"""Rebalancing calculation (spec section 3.7, RB-04 to RB-12, RB-22).

Pure functions on Decimal values, no database access. The rules are based on
the earlier script invest_calc.py (no longer in the repository) with the deliberate
changes listed in the spec:
proportional dip buying against the total value (RB-07), selling to the
midband of the correct final value (RB-08), and full sells of positions with
exit flag or not in the policy (RB-08). Cash leaves the portfolio only as the
withdrawal of a rebalance (RB-22). The calculation works on values; to_units converts
its amounts into units afterwards (RB-24).
"""

from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from enum import StrEnum

from yap.domain.bands import Band, allocation_pct
from yap.domain.types import HUNDRED, TARGET_SUM_TOLERANCE, AssetType
from yap.messages import Message, msg

# Amounts below this are treated as zero, as in invest_calc.py (RB-07)
MIN_AMOUNT = Decimal("0.01")
# Deficits below this many percentage points count as "at target" (RB-10)
MIN_DEFICIT_PCT = Decimal("0.01")
MAX_BUY_ROUNDS = 100
# RB-24: units are calculated with more digits than the default 28, so units held with many
# decimals (crypto) never lose one; fractional units have at most 18 decimals, like ETH
UNITS_PRECISION = 60
FRACTION = Decimal("1E-18")


class RebalancingError(ValueError):
    """An invalid input; `message` has a code, so it can be shown translated (NFR-10)."""

    def __init__(self, message: Message) -> None:
        super().__init__(str(message))
        self.message = message


class TargetSumError(RebalancingError):
    def __init__(self, target_sum: Decimal) -> None:
        self.target_sum = target_sum
        self.difference = target_sum - HUNDRED
        super().__init__(msg("target_sum", sum=str(target_sum), difference=str(self.difference)))


class MultipleCashBuffersError(RebalancingError):
    def __init__(self) -> None:
        super().__init__(msg("multiple_cash_buffers"))


class AmountError(RebalancingError):
    """An invalid contribution or withdrawal (RB-01); `field` names the input."""

    field: str


class NegativeContributionError(AmountError):
    field = "contribution"

    def __init__(self) -> None:
        super().__init__(msg("contribution_min"))


class NegativeWithdrawalError(AmountError):
    field = "withdrawal"

    def __init__(self) -> None:
        super().__init__(msg("withdrawal_min"))


class WithdrawalTooLargeError(AmountError):
    field = "withdrawal"

    def __init__(self, maximum: Decimal) -> None:
        self.maximum = maximum
        super().__init__(msg("withdrawal_too_large", maximum=f"{maximum:.2f}"))


class Phase1Action(StrEnum):
    SELL = "Sell"
    SELL_ALL_EXIT = "Sell All (Exit)"
    BUY_BUFFER = "Buy (Buffer)"
    DEPLOY = "Deploy"
    SELL_AND_DEPLOY = "Sell & Deploy"
    HOLD = "Hold"


class Phase3Action(StrEnum):
    BUY_BELOW_TARGET = "Buy (Below Target)"
    BUY_AT_TARGET = "Buy (At Target)"
    SELL_WITHDRAWAL = "Sell (Withdrawal)"
    HOLD = "Hold"
    EXIT = "-"


@dataclass(frozen=True)
class PositionInput:
    """One position of a portfolio snapshot, with its target from the policy version.

    Positions that are not in the policy version have `in_policy=False` and no band.
    Units, price and whole_units are only used by to_units (RB-24); without units or
    price the position keeps its amounts.
    """

    ticker: str
    name: str
    asset_type: AssetType
    value: Decimal
    band: Band | None = None
    exit: bool = False
    broker: str | None = None
    units: Decimal | None = None
    price: Decimal | None = None
    whole_units: bool | None = None

    @property
    def has_units(self) -> bool:
        """Its amounts can be converted into units (RB-24); never the cash buffer."""
        return (
            self.asset_type is not AssetType.CASH_BUFFER
            and self.units is not None
            and self.price is not None
            and self.price > 0
        )

    @property
    def in_policy(self) -> bool:
        return self.band is not None

    @property
    def sold_completely(self) -> bool:
        return self.exit or not self.in_policy

    @property
    def is_cash_buffer(self) -> bool:
        return self.asset_type is AssetType.CASH_BUFFER and self.in_policy


@dataclass
class PositionResult:
    position: PositionInput
    # Phase 1
    allocation_before_pct: Decimal = Decimal(0)
    buffer_buy: Decimal = Decimal(0)
    buffer_deployed: Decimal = Decimal(0)
    sell_amount: Decimal = Decimal(0)
    value_after_phase1: Decimal = Decimal(0)
    allocation_after_phase1_pct: Decimal = Decimal(0)
    phase1_action: Phase1Action = Phase1Action.HOLD
    # Phase 3
    allocation_before_phase3_pct: Decimal = Decimal(0)
    buy_amount: Decimal = Decimal(0)
    withdrawal_sell: Decimal = Decimal(0)
    value_after_phase3: Decimal = Decimal(0)
    allocation_after_phase3_pct: Decimal = Decimal(0)
    phase3_action: Phase3Action = Phase3Action.HOLD
    # Units of each action and after all actions (RB-24); None without units
    buffer_buy_units: Decimal | None = None
    sell_units: Decimal | None = None
    buy_units: Decimal | None = None
    withdrawal_sell_units: Decimal | None = None
    units_after: Decimal | None = None

    @property
    def difference_to_target_pct(self) -> Decimal | None:
        """Allocation after all actions minus target (RB-11, RB-14)."""
        band = self.position.band
        if band is None:
            return None
        return self.allocation_after_phase3_pct - band.target_pct


@dataclass
class RebalanceResult:
    positions: list[PositionResult]
    contribution: Decimal
    withdrawal: Decimal
    total_value_before: Decimal
    total_buffer_used: Decimal
    total_sell_proceeds: Decimal
    # Phase 2: cash for phase 3 buys, or what phase 3 still has to sell for the withdrawal
    available_cash: Decimal
    total_withdrawal_sells: Decimal
    total_value_after: Decimal
    unallocated_cash: Decimal
    buys_by_broker: dict[str | None, Decimal] = field(default_factory=dict)
    # Part of the unallocated cash left by rounding to whole units (RB-24)
    rounding_cash: Decimal = Decimal(0)


def validate_positions(positions: list[PositionInput]) -> None:
    """Checks RB-04 (targets sum to 100 %) and POL-05 (at most one cash buffer)."""
    in_policy = [p for p in positions if p.band is not None]
    target_sum = sum((p.band.target_pct for p in in_policy if p.band), Decimal(0))
    if abs(target_sum - HUNDRED) > TARGET_SUM_TOLERANCE:
        raise TargetSumError(target_sum)
    if sum(1 for p in in_policy if p.is_cash_buffer) > 1:
        raise MultipleCashBuffersError()


def rebalance(
    positions: list[PositionInput], contribution: Decimal, withdrawal: Decimal = Decimal(0)
) -> RebalanceResult:
    if contribution < 0:
        raise NegativeContributionError()
    if withdrawal < 0:
        raise NegativeWithdrawalError()
    validate_positions(positions)

    results = [PositionResult(position=p) for p in positions]
    values = {id(r): r.position.value for r in results}
    total = sum(values.values(), Decimal(0))
    if withdrawal > total + contribution:
        raise WithdrawalTooLargeError(total + contribution)
    for r in results:
        r.allocation_before_pct = allocation_pct(r.position.value, total)
    final_total = total + contribution - withdrawal

    buffer_used = _phase1a_dip_buying(results, values, total)
    total_sells = _phase1b_sells(results, values, total, final_total)

    value_after_sells = sum(values.values(), Decimal(0))
    for r in results:
        r.value_after_phase1 = values[id(r)]
        r.allocation_after_phase1_pct = allocation_pct(values[id(r)], value_after_sells)
        r.allocation_before_phase3_pct = r.allocation_after_phase1_pct
        r.phase1_action = _phase1_action(r)

    # Phase 2 (RB-09)
    cash = contribution + total_sells - withdrawal
    available = max(cash, Decimal(0))
    to_sell = max(-cash, Decimal(0))

    unallocated = _phase3_buys(results, values, final_total, available)
    _phase3_withdrawal_sells(results, values, final_total, to_sell)

    buys_by_broker: dict[str | None, Decimal] = {}
    for r in results:
        r.value_after_phase3 = values[id(r)]
        r.allocation_after_phase3_pct = allocation_pct(values[id(r)], final_total)
        r.phase3_action = _phase3_action(r)
        if r.buy_amount > 0:
            broker = r.position.broker
            buys_by_broker[broker] = buys_by_broker.get(broker, Decimal(0)) + r.buy_amount

    return RebalanceResult(
        positions=results,
        contribution=contribution,
        withdrawal=withdrawal,
        total_value_before=total,
        total_buffer_used=buffer_used,
        total_sell_proceeds=total_sells,
        available_cash=available,
        total_withdrawal_sells=to_sell,
        total_value_after=final_total - unallocated,
        unallocated_cash=unallocated,
        buys_by_broker=buys_by_broker,
    )


def _phase1a_dip_buying(
    results: list[PositionResult], values: dict[int, Decimal], total: Decimal
) -> Decimal:
    """RB-07: distribute the cash buffer proportionally to the dip depth."""
    buffer = next((r for r in results if r.position.is_cash_buffer and not r.position.exit), None)
    if buffer is None or buffer.position.value <= 0:
        return Decimal(0)

    # Remaining amount each candidate needs to reach its buy threshold, and its
    # deficit in percentage points, which is its weight.
    need: dict[int, Decimal] = {}
    weight: dict[int, Decimal] = {}
    for r in results:
        p = r.position
        if p.band is None or p.is_cash_buffer or p.exit:
            continue
        if r.allocation_before_pct < p.band.buy_abs:
            need[id(r)] = p.band.buy_abs / HUNDRED * total - p.value
            weight[id(r)] = p.band.buy_abs - r.allocation_before_pct

    remaining = buffer.position.value
    bought = {key: Decimal(0) for key in need}
    active = set(need)
    while active and remaining > 0:
        weight_sum = sum(weight[k] for k in active)
        shares = {k: remaining * weight[k] / weight_sum for k in active}
        capped = {k for k in active if shares[k] >= need[k] - bought[k]}
        if not capped:
            for k in active:
                bought[k] += shares[k]
            remaining = Decimal(0)
            break
        # Fill the capped candidates up to their threshold and redistribute the rest
        for k in capped:
            remaining -= need[k] - bought[k]
            bought[k] = need[k]
        active -= capped

    used = Decimal(0)
    by_id = {id(r): r for r in results}
    for key, amount in bought.items():
        if amount < MIN_AMOUNT:
            continue
        by_id[key].buffer_buy = amount
        values[key] += amount
        used += amount
    buffer.buffer_deployed = used
    values[id(buffer)] -= used
    return used


def _phase1b_sells(
    results: list[PositionResult],
    values: dict[int, Decimal],
    total: Decimal,
    final: Decimal,
) -> Decimal:
    """RB-08: full sells (exit, not in policy) and sells down to the midband of the
    final value F = V + C - W."""
    full_sells = Decimal(0)
    candidates: list[PositionResult] = []
    for r in results:
        p = r.position
        value = values[id(r)]
        if p.sold_completely:
            if value > 0:
                r.sell_amount = value
                full_sells += value
        elif p.band is not None and allocation_pct(value, total) > p.band.sell_abs:
            candidates.append(r)

    # Each candidate i is sold to midband m_i: sell_i = v_i - m_i × F. A large
    # contribution can lift F so far that a candidate needs no sell.
    threshold_sells = Decimal(0)
    for r in candidates:
        assert r.position.band is not None
        amount = values[id(r)] - r.position.band.midband / HUNDRED * final
        if amount > 0:
            r.sell_amount = amount
            threshold_sells += amount

    for r in results:
        values[id(r)] -= r.sell_amount
    return full_sells + threshold_sells


def _phase3_buys(
    results: list[PositionResult],
    values: dict[int, Decimal],
    final_total: Decimal,
    available: Decimal,
) -> Decimal:
    """RB-10: deficit²-weighted buys capped at target, rest proportional to target.

    Returns the cash that could not be allocated (no eligible position with a target).
    """
    if available <= 0:
        return Decimal(0)
    eligible = [
        r
        for r in results
        if r.position.band is not None and not r.position.exit and r.sell_amount == 0
    ]
    target_sum = sum((r.position.band.target_pct for r in eligible if r.position.band), Decimal(0))
    if not eligible or target_sum == 0:
        return available

    remaining = available
    for _ in range(MAX_BUY_ROUNDS):
        if remaining <= MIN_AMOUNT:
            break
        weights: dict[int, Decimal] = {}
        for r in eligible:
            assert r.position.band is not None
            current = allocation_pct(values[id(r)] + r.buy_amount, final_total)
            deficit = r.position.band.target_pct - current
            if deficit > MIN_DEFICIT_PCT:
                weights[id(r)] = deficit * deficit
        if not weights:
            break
        weight_sum = sum(weights.values(), Decimal(0))
        distributed = Decimal(0)
        for r in eligible:
            if id(r) not in weights:
                continue
            assert r.position.band is not None
            proposed = weights[id(r)] / weight_sum * remaining
            to_target = (
                r.position.band.target_pct / HUNDRED * final_total - values[id(r)] - r.buy_amount
            )
            amount = min(proposed, to_target)
            r.buy_amount += amount
            distributed += amount
        remaining -= distributed
        if distributed < MIN_AMOUNT:
            break

    # Whatever is left (all at target, no progress, or a residue) is distributed
    # in proportion to target, so no cash is lost.
    if remaining > 0:
        for r in eligible:
            assert r.position.band is not None
            r.buy_amount += remaining * r.position.band.target_pct / target_sum

    for r in eligible:
        values[id(r)] += r.buy_amount
    return Decimal(0)


def _phase3_withdrawal_sells(
    results: list[PositionResult],
    values: dict[int, Decimal],
    final_total: Decimal,
    to_sell: Decimal,
) -> None:
    """RB-22: surplus²-weighted sells capped at target, rest proportional to target."""
    if to_sell <= 0:
        return
    eligible = [
        r
        for r in results
        if r.position.band is not None and not r.position.exit and r.sell_amount == 0
    ]

    def left(r: PositionResult) -> Decimal:
        return values[id(r)] - r.withdrawal_sell

    remaining = to_sell
    for _ in range(MAX_BUY_ROUNDS):
        if remaining <= MIN_AMOUNT:
            break
        weights: dict[int, Decimal] = {}
        for r in eligible:
            assert r.position.band is not None
            surplus = allocation_pct(left(r), final_total) - r.position.band.target_pct
            if surplus > MIN_DEFICIT_PCT:
                weights[id(r)] = surplus * surplus
        if not weights:
            break
        weight_sum = sum(weights.values(), Decimal(0))
        distributed = Decimal(0)
        for r in eligible:
            if id(r) not in weights:
                continue
            assert r.position.band is not None
            proposed = weights[id(r)] / weight_sum * remaining
            to_target = left(r) - r.position.band.target_pct / HUNDRED * final_total
            amount = min(proposed, to_target)
            r.withdrawal_sell += amount
            distributed += amount
        remaining -= distributed
        if distributed < MIN_AMOUNT:
            break

    # The rest in proportion to target, each capped at what is left of the position
    active = [r for r in eligible if r.position.band and r.position.band.target_pct > 0]
    while remaining > 0:
        active = [r for r in active if left(r) > 0]
        if not active:  # pragma: no cover - see the fallback below
            break
        target_sum = sum(
            (r.position.band.target_pct for r in active if r.position.band), Decimal(0)
        )
        shares = {
            id(r): remaining * r.position.band.target_pct / target_sum
            for r in active
            if r.position.band
        }
        capped = [r for r in active if shares[id(r)] >= left(r)]
        if not capped:
            for r in active:
                r.withdrawal_sell += shares[id(r)]
            remaining = Decimal(0)
            break
        for r in capped:
            remaining -= left(r)
            r.withdrawal_sell += left(r)

    # Not reachable with valid inputs (positions sold in 1B end on midbands that sum to
    # less than 100 %); kept so a withdrawal is never silently short. A random search over
    # 80'000 portfolios did not reach it, so it is excluded from the coverage rule (NFR-12).
    if remaining > 0:  # pragma: no cover
        holders = [r for r in results if left(r) > 0]
        held = sum((left(r) for r in holders), Decimal(0))
        for r in holders:
            r.withdrawal_sell += remaining * left(r) / held

    for r in results:
        values[id(r)] -= r.withdrawal_sell


# --- Units (RB-24) --------------------------------------------------------------


def _down(units: Decimal, whole: bool) -> Decimal:
    if whole:
        return units.to_integral_value(rounding=ROUND_FLOOR)
    return units.quantize(FRACTION, rounding=ROUND_FLOOR)


def _up(units: Decimal, whole: bool) -> Decimal:
    if whole:
        return units.to_integral_value(rounding=ROUND_CEILING)
    return units.quantize(FRACTION, rounding=ROUND_CEILING)


def _buy_units(amount: Decimal, price: Decimal, whole: bool) -> tuple[Decimal, Decimal]:
    """(units, amount) of a buy, rounded down; whole units also change the amount, the
    18th decimal of fractional units does not."""
    units = _down(amount / price, whole)
    return (units, units * price) if whole else (units, amount)


def _sell_units(
    amount: Decimal, price: Decimal, whole: bool, units_left: Decimal, value_left: Decimal
) -> tuple[Decimal, Decimal]:
    """(units, amount) of a sell, rounded up, never above the units left. Selling all units
    left sells their value, never less than the calculation sold."""
    units = min(_up(amount / price, whole), units_left)
    if not whole:
        return units, amount
    return (units, value_left) if units == units_left and amount > 0 else (units, units * price)


def _position_units(r: PositionResult) -> Decimal:
    """Converts one position's actions into units; returns how much of its buffer buy the
    rounding leaves in the cash buffer."""
    p = r.position
    assert p.units is not None and p.price is not None
    price, whole = p.price, p.whole_units is True
    r.buffer_buy_units, rounded = _buy_units(r.buffer_buy, price, whole)
    kept = r.buffer_buy - rounded
    r.buffer_buy = rounded
    held_units = p.units + r.buffer_buy_units
    held_value = p.value + r.buffer_buy
    if p.sold_completely and r.sell_amount > 0:
        r.sell_units, r.sell_amount = held_units, held_value
    else:
        r.sell_units, r.sell_amount = _sell_units(
            r.sell_amount, price, whole, held_units, held_value
        )
    r.buy_units, r.buy_amount = _buy_units(r.buy_amount, price, whole)
    r.withdrawal_sell_units, r.withdrawal_sell = _sell_units(
        r.withdrawal_sell, price, whole, held_units - r.sell_units, held_value - r.sell_amount
    )
    r.units_after = held_units - r.sell_units + r.buy_units - r.withdrawal_sell_units
    return kept


def to_units(result: RebalanceResult) -> RebalanceResult:
    """RB-24: converts the amounts of the calculation into units at the position's price.

    For positions traded in whole units only, buys are rounded down and sells up, a sell
    never above the units held; a complete sell (exit, not in policy) sells all units. The
    amounts of rounded actions become units x price. Cash freed or not spent by rounding is
    not redistributed: it is unallocated cash. Changes `result` in place and returns it;
    without any position with units it stays exactly as calculated.
    """
    if not any(r.position.has_units for r in result.positions):
        return result
    # Only the units need the extra digits; amounts and totals stay as in the calculation
    with localcontext() as context:
        context.prec = UNITS_PRECISION
        # Buffer buys rounded down leave more in the cash buffer
        buffer_kept = sum(
            (_position_units(r) for r in result.positions if r.position.has_units), Decimal(0)
        )

    final_total = result.total_value_before + result.contribution - result.withdrawal
    values: dict[int, Decimal] = {}
    for r in result.positions:
        if r.position.is_cash_buffer:
            r.buffer_deployed -= buffer_kept
        deployed = r.buffer_deployed if r.position.is_cash_buffer else Decimal(0)
        values[id(r)] = r.position.value + r.buffer_buy - r.sell_amount - deployed
    value_after_sells = sum(values.values(), Decimal(0))
    buys_by_broker: dict[str | None, Decimal] = {}
    for r in result.positions:
        r.value_after_phase1 = values[id(r)]
        r.allocation_after_phase1_pct = allocation_pct(values[id(r)], value_after_sells)
        r.allocation_before_phase3_pct = r.allocation_after_phase1_pct
        r.phase1_action = _phase1_action(r)
        r.value_after_phase3 = values[id(r)] + r.buy_amount - r.withdrawal_sell
        r.allocation_after_phase3_pct = allocation_pct(r.value_after_phase3, final_total)
        r.phase3_action = _phase3_action(r)
        if r.buy_amount > 0:
            broker = r.position.broker
            buys_by_broker[broker] = buys_by_broker.get(broker, Decimal(0)) + r.buy_amount

    sells = sum((r.sell_amount for r in result.positions), Decimal(0))
    withdrawal_sells = sum((r.withdrawal_sell for r in result.positions), Decimal(0))
    buys = sum((r.buy_amount for r in result.positions), Decimal(0))
    cash = result.contribution + sells - result.withdrawal
    unallocated = cash + withdrawal_sells - buys
    result.rounding_cash = unallocated - result.unallocated_cash
    result.total_buffer_used -= buffer_kept
    result.total_sell_proceeds = sells
    result.available_cash = max(cash, Decimal(0))
    result.total_withdrawal_sells = max(-cash, Decimal(0))
    result.unallocated_cash = unallocated
    result.total_value_after = final_total - unallocated
    result.buys_by_broker = buys_by_broker
    return result


def _phase1_action(r: PositionResult) -> Phase1Action:
    p = r.position
    if p.sold_completely:
        return Phase1Action.SELL_ALL_EXIT
    if p.is_cash_buffer and r.buffer_deployed > 0:
        return Phase1Action.SELL_AND_DEPLOY if r.sell_amount > 0 else Phase1Action.DEPLOY
    if r.sell_amount > 0:
        return Phase1Action.SELL
    if r.buffer_buy > 0:
        return Phase1Action.BUY_BUFFER
    return Phase1Action.HOLD


def _phase3_action(r: PositionResult) -> Phase3Action:
    p = r.position
    if p.sold_completely or p.band is None:
        return Phase3Action.EXIT
    if r.withdrawal_sell > 0:
        return Phase3Action.SELL_WITHDRAWAL
    if r.sell_amount > 0 or r.buy_amount <= 0:
        return Phase3Action.HOLD
    if r.allocation_before_pct < p.band.target_pct:
        return Phase3Action.BUY_BELOW_TARGET
    return Phase3Action.BUY_AT_TARGET
