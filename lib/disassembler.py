import json

from capstone import *
from capstone.arm64_const import *
from PyQt5.QtCore import QThread, pyqtSignal

from lib.types.instruction import Instruction


class DisassembleThread(QThread):
    onFinished = pyqtSignal(list, name='onFinished')
    onError = pyqtSignal(str, name='onError')

    def __init__(self, dwarf, capstone, dwarf_range, num_instructions=0):
        super().__init__()
        self._dwarf = dwarf
        self._range = dwarf_range
        self._capstone = capstone
        self._num_instructions = num_instructions
        self._max_instruction = 1024

        self._counter = 0
        self._instructions = []

        self._debug_symbols = []
        self._debug_symbols_indexes = []

        if self._range is not None and self._range.data is not None:
            for cap_inst in self._capstone.disasm(
                    self._range.data[self._range.user_req_start_offset:], self._range.user_req_start_address):
                self._counter += 1

                if 0 < self._num_instructions < self._counter:
                    break

                dwarf_instruction = Instruction(self._dwarf, cap_inst)
                if dwarf_instruction.is_jump and dwarf_instruction.jump_address:
                    self._debug_symbols.append(dwarf_instruction.jump_address)
                    self._debug_symbols_indexes.append(str(len(self._instructions)))
                elif dwarf_instruction.is_call and dwarf_instruction.call_address:
                    self._debug_symbols.append(dwarf_instruction.call_address)
                    self._debug_symbols_indexes.append(str(len(self._instructions)))

                if self._num_instructions < 1:
                    if cap_inst.group(CS_GRP_RET) or cap_inst.group(ARM64_GRP_RET) or \
                            self._counter > self._max_instruction:
                        break

                self._instructions.append(dwarf_instruction)

    def run(self):
        if self._range is None:
            self.onError.emit('No Range set')
            self.onFinished.emit([])

        if self._range.data is not None:
            if len(self._debug_symbols) > 0:
                symbols = self._dwarf.dwarf_api('getDebugSymbols', json.dumps(self._debug_symbols))
                if symbols:
                    for i in range(len(symbols)):
                        symbol = symbols[i]
                        instruction = self._instructions[int(self._debug_symbols_indexes[i])]
                        instruction.symbol_name = symbol['name']
                        instruction.symbol_module = '-'
                        if 'moduleName' in symbol:
                            instruction.symbol_module = symbol['moduleName']

        self.onFinished.emit(self._instructions)


class Disassembler:
    def __init__(self, dwarf):
        self.dwarf = dwarf

        self.dwarf.onApplyContext.connect(self.on_arch_changed)

        self._capstone = None
        self._disasm_thread = None

        self.capstone_arch = 0
        self.capstone_mode = 0
        self.keystone_arch = 0
        self.keystone_mode = 0

        self.on_arch_changed()

    def disasm(self, dwarf_range, callback, num_instructions=0):
        self._disasm_thread = DisassembleThread(
            self.dwarf, self._capstone, dwarf_range, num_instructions=num_instructions)
        self._disasm_thread.onFinished.connect(callback)
        self._disasm_thread.start(QThread.HighestPriority)

    def on_arch_changed(self):
        if self.dwarf.arch == 'arm64':
            self.capstone_arch = CS_ARCH_ARM64
            self.capstone_mode = CS_MODE_LITTLE_ENDIAN
        elif self.dwarf.arch == 'arm':
            self.capstone_arch = CS_ARCH_ARM
            context = self.dwarf.current_context()
            self.capstone_mode = CS_MODE_ARM
            if context is not None and context.is_native_context:
                if context.pc.thumb:
                    self.capstone_mode = CS_MODE_THUMB
        elif self.dwarf.arch == 'ia32':
            self.capstone_arch = CS_ARCH_X86
            self.capstone_mode = CS_MODE_32
        elif self.dwarf.arch == 'x64':
            self.capstone_arch = CS_ARCH_X86
            self.capstone_mode = CS_MODE_64
        if self.dwarf.keystone_installed:
            import keystone.keystone_const as ks
            if self.dwarf.arch == 'arm64':
                self.keystone_arch = ks.KS_ARCH_ARM64
                self.keystone_mode = ks.KS_MODE_LITTLE_ENDIAN
            elif self.dwarf.arch == 'arm':
                self.keystone_arch = ks.KS_ARCH_ARM
                self.keystone_mode = ks.KS_MODE_ARM
            elif self.dwarf.arch == 'ia32':
                self.keystone_arch = ks.KS_ARCH_X86
                self.keystone_mode = ks.KS_MODE_32
            elif self.dwarf.arch == 'x64':
                self.keystone_arch = ks.KS_ARCH_X86
                self.keystone_mode = ks.KS_MODE_64

        self._capstone = Cs(self.capstone_arch, self.capstone_mode)
        self._capstone.detail = True
        # self._capstone.skipdata = True
