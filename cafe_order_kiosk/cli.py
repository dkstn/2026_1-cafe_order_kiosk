from __future__ import annotations

import shlex
from dataclasses import dataclass

from cafe_order_kiosk.models import OrderStatus
from cafe_order_kiosk.kiosk_store import KioskStore
from cafe_order_kiosk.utils import format_money
from datetime import timezone, timedelta

@dataclass
class CLIState:
    current_order_id: int | None = None


def run_cli() -> int:
    store = KioskStore.with_default_menu()
    state = CLIState()

    print("카페 주문 키오스크")
    print("명령어 목록은 '도움말'을 입력하세요. 가격은 원 단위 정수입니다.")

    while True:
        try:
            raw = input("kiosk> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        tokens = shlex.split(raw)
        command, args = tokens[0], tokens[1:]

        if command in {"종료", "끝", "quit", "exit"}:
            break
        elif command in {"도움말", "help"}:
            print_help()
        elif command in {"메뉴", "menu"}:
            handle_menu(store)
        elif command in {"주문", "order"}:
            handle_order(store, state, args)
        elif command in {"주문목록", "orders"}:
            handle_orders(store, args)
        elif command in {"결제", "pay"}:
            handle_pay(store, state, args)
        else:
            print("알 수 없는 명령입니다. '도움말'을 입력하세요.")
    print("종료합니다.")
    return 0


def print_help() -> None:
    print("명령어:")
    print("\t메뉴")
    print("\t주문 생성 [메모]")
    print("\t주문 선택 <주문_id>")
    print("\t주문 추가 <메뉴_id> <수량> [옵션]")
    print("\t주문 삭제 <라인번호>")
    print("\t주문 조회")
    print("\t주문 취소")
    print("\t주문목록 목록 [진행중|결제완료|취소]")
    print("\t결제 <방법> [금액]")
    print("\t도움말")
    print("\t종료")


def handle_menu(store: KioskStore) -> None:
    print("메뉴:")
    for item in store.list_menu():
        description = f" - {item.description}" if item.description else ""
        print(
            f"\t{item.id}. {item.name} ({item.category}) - {format_money(item.price)}"
            f"{description}"
        )


def handle_order(store: KioskStore, state: CLIState, args: list[str]) -> None:
    if not args:
        print("주문 명령어: 생성, 선택, 추가, 삭제, 조회, 취소")
        return

    action, tail = args[0], args[1:]

    if action in {"생성", "new"}:
        note = " ".join(tail).strip() if tail else None
        order = store.create_order(note=note)
        state.current_order_id = order.id
        print(f"주문 #{order.id}가 생성되었습니다.")
    elif action in {"선택", "select"}:
        order_id = parse_int_arg(tail, "order_id")
        if order_id is None:
            return
        order = store.get_order(order_id)
        if order is None:
            print("주문을 찾을 수 없습니다.")
            return
        state.current_order_id = order.id
        print(f"주문 #{order.id}를 선택했습니다.")
    elif action in {"추가", "add"}:
        if state.current_order_id is None:
            print("선택된 주문이 없습니다. 먼저 '주문 생성'을 사용하세요.")
            return
        if len(tail) < 2:
            print("사용법: 주문 추가 <메뉴_id> <수량> [옵션]")
            return
        menu_id = parse_int_arg(tail[:1], "menu_id")
        quantity = parse_int_arg(tail[1:2], "qty")
        if menu_id is None or quantity is None:
            return

        options_text = " ".join(tail[2:]).strip()
        options = (
            [option.strip() for option in options_text.split(",") if option.strip()]
            if options_text
            else []
        )
        try:
            store.add_item(state.current_order_id, menu_id, quantity, options)
        except ValueError as exc:
            print(str(exc))
            return
        print("항목이 추가되었습니다.")
    elif action in {"삭제", "remove"}:
        if state.current_order_id is None:
            print("선택된 주문이 없습니다. 먼저 '주문 생성'을 사용하세요.")
            return
        line_index = parse_int_arg(tail, "line_index")
        if line_index is None:
            return
        try:
            store.remove_item(state.current_order_id, line_index)
        except ValueError as exc:
            print(str(exc))
            return
        print("항목이 삭제되었습니다.")
    elif action in {"조회", "show"}:
        if state.current_order_id is None:
            print("선택된 주문이 없습니다. 먼저 '주문 생성'을 사용하세요.")
            return
        order = store.get_order(state.current_order_id)
        if order is None:
            print("주문을 찾을 수 없습니다.")
            return
        print_order(order)
    elif action in {"취소", "cancel"}:
        if state.current_order_id is None:
            print("선택된 주문이 없습니다. 먼저 '주문 생성'을 사용하세요.")
            return
        try:
            order = store.cancel_order(state.current_order_id)
        except ValueError as exc:
            print(str(exc))
            return
        print(f"주문 #{order.id}가 취소되었습니다.")
    else:
        print("알 수 없는 주문 명령어입니다.")


def handle_orders(store: KioskStore, args: list[str]) -> None:
    if not args or args[0] not in {"list", "목록"}:
        print("사용법: 주문목록 목록 [진행중|결제완료|취소]")
        return

    status = None
    if len(args) > 1:
        status = parse_status(args[1])
        if status is None:
            return

    orders = store.list_orders(status)
    if not orders:
        print("주문이 없습니다.")
        return

    for order in orders:
        print(
            f"  #{order.id} {format_status(order.status)} - {format_money(order.total)}"
        )


def handle_pay(store: KioskStore, state: CLIState, args: list[str]) -> None:
    if state.current_order_id is None:
        print("선택된 주문이 없습니다. 먼저 '주문 생성'을 사용하세요.")
        return
    if not args:
        print("사용법: 결제 <방법> [금액]")
        return

    method = args[0]
    amount = None
    if len(args) > 1:
        amount = parse_int_arg(args[1:2], "amount")
        if amount is None:
            return

    order = store.get_order(state.current_order_id)
    if order is None:
        print("주문을 찾을 수 없습니다.")
        return
    if amount is None:
        amount = order.total

    try:
        store.pay_order(order.id, method, amount)
        order = store.get_order(order.id)
        
    except ValueError as exc:
        print(str(exc))
        return

    print(f"주문 #{order.id} 결제 완료 ({method}).")
    save_order_to_file(order)


def print_order(order) -> None:
    print(f"주문 #{order.id} ({format_status(order.status)})")
    if order.note:
        print(f"메모: {order.note}")
    if not order.items:
        print("  (비어 있음)")
        return

    for idx, item in enumerate(order.items, start=1):
        options = f" [{', '.join(item.options)}]" if item.options else ""
        print(
            f"  {idx}. {item.name}{options} x{item.quantity}"
            f" - {format_money(item.line_total)}"
        )
    print(f"합계: {format_money(order.total)}")


def parse_int_arg(args: list[str], name: str) -> int | None:
    if not args:
        print(f"필수 값이 없습니다: {name}")
        return None
    try:
        return int(args[0])
    except ValueError:
        print(f"잘못된 값: {name}")
        return None


def parse_status(raw: str) -> OrderStatus | None:
    normalized = raw.lower()
    status_map = {
        "open": OrderStatus.OPEN,
        "paid": OrderStatus.PAID,
        "canceled": OrderStatus.CANCELED,
        "진행중": OrderStatus.OPEN,
        "결제완료": OrderStatus.PAID,
        "취소": OrderStatus.CANCELED,
    }
    status = status_map.get(normalized)
    if status is None:
        print("잘못된 상태입니다. 진행중, 결제완료, 취소 중에서 선택하세요.")
    return status

def format_status(status: OrderStatus) -> str:
    status_map = {
        OrderStatus.OPEN: "진행중",
        OrderStatus.PAID: "결제완료",
        OrderStatus.CANCELED: "취소",
    }
    return status_map.get(status, status.value)

# 주문 완료 시 주문 내역을 파일로 저장하는 함수
def save_order_to_file(order):
    filename = "orders.txt"

    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"\n===== 주문 ID: {order.id} =====\n")

        # UTC 시간을 한국 시간으로 변환하여 사용자가 보기 쉽게 처리
        korea_time = order.created_at + timedelta(hours=9)
        formatted_time = korea_time.strftime("%Y-%m-%d %H:%M")

        f.write(f"주문 시간: {formatted_time}\n")

        # 주문에 포함된 각 메뉴 항목을 파일에 기록
        for item in order.items:
            f.write(f"{item.name} x{item.quantity} ({item.line_total}원)\n")

        # 주문의 총 금액을 파일에 기록
        f.write(f"총 금액: {order.total}원\n")
