"""Money is stored as whole centavos (int) and shown as pesos: 123450 -> "₱1,234.50"."""
import re
from decimal import Decimal

# ₱10,000,000.00. Big enough for one person, and small enough for a
# PostgreSQL INTEGER column (the biggest is about ₱21 million in centavos).
MAX_CENTAVOS = 10_000_000_00

AMOUNT_PATTERN = re.compile(r"-?\d+(\.\d{1,2})?")


def peso(centavos, signed=False):
    """Format centavos as pesos. signed=True adds "+" to amounts above zero."""
    centavos = int(centavos or 0)
    sign = "−" if centavos < 0 else ("+" if signed and centavos > 0 else "")
    pesos, cents = divmod(abs(centavos), 100)
    return f"{sign}₱{pesos:,}.{cents:02d}"


def parse_amount(text, allow_negative=False):
    """Read what a person typed ("1,234.50", "₱150", "99.5") as centavos.

    Returns None for anything else: words, three decimals, too big, and
    negative numbers unless allow_negative is True. We use Decimal, not
    float, because float("0.29") * 100 is 28.999999999999996.
    """
    text = (text or "").replace("₱", "").replace(",", "").replace(" ", "")
    if text.upper().startswith("PHP"):
        text = text[3:]
    if not AMOUNT_PATTERN.fullmatch(text):
        return None
    centavos = int(Decimal(text) * 100)
    if abs(centavos) > MAX_CENTAVOS or (centavos < 0 and not allow_negative):
        return None
    return centavos


def amount_input(centavos):
    """Centavos as the plain text an input box shows: 123450 -> "1234.50"."""
    if centavos is None:
        return ""
    sign = "-" if centavos < 0 else ""
    pesos, cents = divmod(abs(int(centavos)), 100)
    return f"{sign}{pesos}.{cents:02d}"
