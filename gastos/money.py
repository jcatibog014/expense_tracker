"""Money is stored as whole centavos (int) and shown as pesos: 123450 -> "₱1,234.50"."""


def peso(centavos, signed=False):
    """Format centavos as pesos. signed=True adds "+" to amounts above zero."""
    centavos = int(centavos or 0)
    sign = "−" if centavos < 0 else ("+" if signed and centavos > 0 else "")
    pesos, cents = divmod(abs(centavos), 100)
    return f"{sign}₱{pesos:,}.{cents:02d}"
