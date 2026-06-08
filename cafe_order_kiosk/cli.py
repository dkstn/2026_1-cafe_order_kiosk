from __future__ import annotations

import shlex
from dataclasses import dataclass

from cafe_order_kiosk.models import OrderStatus
from cafe_order_kiosk.kiosk_store import KioskStore
from cafe_order_kiosk.utils import format_money


@dataclass
class CLIState:
    current_order_id: int | None = None
    discount_rate: float = 0.0 #적용된 할인율(0.1 = 10%)


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
        elif command in {"쿠폰", "coupon"}:
            handle_coupon(state, args)
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
        total = order.total
        # 적용된 할인율을 바탕으로 결제 금액을 계산
        discount = int(total * state.discount_rate)
        final_total = total - discount
        
        percent = int(state.discount_rate * 100)

        # 원래 금액과 할인율과 할인 금액 및 할인이 적용된 최종 금액을 알려주기 위한 메세지 출력.
        print(f"원래 금액: {total}원")
        print(f"적용된 할인율: {percent}%")
        print(f"할인 금액: {discount}원")
        print(f"최종 결제 금액: {final_total}원")
        
        amount = total


    try:
        store.pay_order(order.id, method, amount)
    except ValueError as exc:
        print(str(exc))
        return

    print(f"주문 #{order.id} 결제 완료 ({method}).")

    # 결제 후 할인율 초기화
    state.discount_rate = 0.0


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


# 할인 쿠폰을 적용하는 함수
def handle_coupon(state: CLIState, args: list[str]) -> None:
    if not args:
        print("쿠폰 코드를 입력하세요(10,20 쿠폰만 존재). 예: 쿠폰 할인10")
        return

    code = args[0]

    # 할인쿠폰이 10%인 경우
    if code == "할인10":
        state.discount_rate = 0.1
        print("10% 할인 쿠폰1이 적용되었습니다.")
    #할인쿠폰이 20%인 경우
    elif code == "할인20":
        state.discount_rate = 0.2
        print("20% 할인 쿠폰이 적용되었습니다.")
    else:
        print("유효하지 않은 쿠폰입니다.")

