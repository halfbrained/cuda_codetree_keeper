import os
import json

from cudatext import *

# DBG
from time import time as t

# file:///install.inf
dir_settings    = app_path(APP_DIR_SETTINGS)
fn_data         = os.path.join(dir_settings, 'codetree_data.json')
fn_config       = os.path.join(dir_settings, 'plugins.ini')

USER_DIR = os.path.expanduser('~')

states = {
    APPSTATE_CODETREE_CLEAR:           'tree_CLEAR',
    APPSTATE_CODETREE_BEFORE_FILL:     'tree_BEFORE_FILL',
    APPSTATE_CODETREE_AFTER_FILL:      'tree_AFTER_FILL',
    APPSTATE_CODETREE_SET_SELECTION:   'tree_SET_SELECTION',
}

LOG = False

opt_max_history = 16
SPL = chr(1)

def collapse_path(path):
    if path  and  (path + os.sep).startswith(USER_DIR + os.sep):
        path = path.replace(USER_DIR, '~', 1)
    return path


class Command:

    def __init__(self):
        global opt_max_history

        opt_max_history = int(ini_read(fn_config, 'codetree_keeper', 'max_history', str(opt_max_history)))

        self._unfolded = {} # filepath -> [node path, ...]
        self._fn_order = [] # most recently acccessed - last

        self.previous_fn = None

        self.load_state()

    def config(self):
        ini_write(fn_config, 'codetree_keeper', 'max_history', str(opt_max_history))
        file_open(fn_config)
        # show my section
        try:
            ind = ed.get_text_all().splitlines().index('[codetree_keeper]')
            ed.set_prop(PROP_LINE_TOP, max(0, ind-3))
            ed.set_caret(0, ind, 18, ind)
        except:
            pass

    def save_state(self):
        """ order - last used is last in list
        """
        jl = []
        for fn in self._fn_order[-opt_max_history:]:
            unfolded = self._unfolded.get(fn)
            if unfolded:
                jl.append( (collapse_path(fn), unfolded) )

        if jl  or  os.path.exists(fn_data):
            jstr = json.dumps(jl, separators=(',', ':'))
            with open(fn_data, 'w', encoding='utf-8') as f:
                f.write(jstr)

    def load_state(self):
        if os.path.exists(fn_data):
            with open(fn_data, 'r', encoding='utf-8') as f:
                state = json.load(f)

            for fn, unfolded in state:
                fn = os.path.expanduser(fn)
                self._unfolded[fn] = unfolded
                self._fn_order.append(fn)


    def on_state(self, ed_self, state):
        if LOG:
            state_s = states.get(state)
            if state_s:
                print(f'        --tree:[[{t():.3f}]] {state_s}: {ed.get_filename() if ed else "no ed"}')

        if state == APPSTATE_CODETREE_CLEAR:
            if self._store_unfolded():
                pass;       #LOG and print(f'-> Clearing:  SAVED:  {self.previous_fn} ->> {self._unfolded.get(self.previous_fn)}')

            callback_str = 'module=cuda_codetree_keeper;cmd=on_after_cleared;info="";'
            timer_proc(TIMER_START_ONE, callback_str, 0)

            self.previous_fn = ed.get_filename()

        elif state == APPSTATE_CODETREE_BEFORE_FILL:
            if self._store_unfolded():
                pass;       #LOG and print(f'-> Before fill: SAVED: {self.previous_fn} ->> {self._unfolded.get(self.previous_fn)}')

            self.previous_fn = ed.get_filename()

        elif state == APPSTATE_CODETREE_AFTER_FILL:
            self._restore_unfolded()

    def on_exit(self, ed_self):
        self._store_unfolded()

        self.save_state()


    def on_after_cleared(self, data='', info=''):
        self._restore_unfolded()


    def _store_unfolded(self):
        h_tree = app_proc(PROC_GET_CODETREE, "")
        unfolded = []
        self._gather_unfolded(h_tree, unfolded)
        if unfolded:
            if self.previous_fn:
                # tree state
                self._unfolded[self.previous_fn] = unfolded
                # access order
                try:
                    self._fn_order.remove(self.previous_fn)
                except ValueError:
                    pass
                self._fn_order.append(self.previous_fn)

                if len(self._fn_order) > opt_max_history*2:
                    del self._fn_order[:-opt_max_history]

                return True


    def _restore_unfolded(self):
        fn = ed.get_filename()
        unfolded = self._unfolded.get(fn)
        pass;       #LOG and print(f'->>>  UNFolding: {(unfolded,)}: {fn}')

        if fn and unfolded:
            h_tree = app_proc(PROC_GET_CODETREE, "")

            for path in unfolded:
                spl = [name for name in path.strip(SPL).split(SPL)]
                self._unfold_by_path(h_tree, spl)


    def _unfold_by_path(self, h_tree, path_names, parent_id=0):
        items = tree_proc(h_tree, TREE_ITEM_ENUM, id_item=parent_id)
        if not items:
            pass;       #LOG and print(f'NOTE:       no items to unfold by path: {path_names}')
            return

        target_name = path_names[0]
        for item_id,caption in items:
            if caption == target_name:
                tree_proc(h_tree, TREE_ITEM_UNFOLD, id_item=item_id)
                pass;       #LOG and print(f'! unfolded : {path_names}')

                if len(path_names) > 1:
                    del path_names[0]
                    return self._unfold_by_path(h_tree, path_names, parent_id = item_id)

                return True

        else:
            pass;       #LOG and print(f'TreeKeepError: cant find item: "{target_name}" in items: {items}: {ed.get_filename()}')


    def _gather_unfolded(self, h_tree, result: list, parent_id=0, path=''):
        chs = tree_proc(h_tree, TREE_ITEM_ENUM_EX, id_item=parent_id)
        if chs is None:
            pass;       #LOG and print(f'NOTE:       None enumer in "_gather_unfolded", path: {path}')
            return

        for item in chs:
            if not item.get('sub_items'):
                continue

            item_id = item['id']
            props = tree_proc(h_tree, TREE_ITEM_GET_PROPS, id_item=item_id)
            if not props['folded']:
                current_path = path +SPL+ props['text']
                result.append(current_path)

                self._gather_unfolded(h_tree, result, parent_id=item_id, path=current_path)
