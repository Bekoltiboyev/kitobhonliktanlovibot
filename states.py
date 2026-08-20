from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    waiting_fullname = State()
    waiting_phone = State()


class PaymentFlow(StatesGroup):
    waiting_receipt = State()


class AdminFlow(StatesGroup):
    waiting_reject_reason = State()
    waiting_block_reason = State()
    # Yangi holatlar:
    waiting_test_time = State()
    waiting_excel_file = State()
    waiting_manual_block = State()
    waiting_manual_unblock = State()