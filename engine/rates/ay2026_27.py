"""Rates, slabs and ceilings for AY 2026-27 (FY 2025-26).

One file per assessment year, and nothing in engine/compute.py hardcodes a
number that belongs here. Next year you copy this file and change it, and the
computation code does not move.

VERIFY BEFORE FILING. These figures are transcribed from the Finance Act 2025
position for FY 2025-26 and have not been reconciled against the department's
released ITR-3 utility for AY 2026-27.
"""

AY = "2026-27"
FY = "2025-26"

# --- Slabs: (upper_bound_or_None, rate) applied to the slice below the bound ---

SLABS_NEW = [
    (400_000, 0.00),
    (800_000, 0.05),
    (1_200_000, 0.10),
    (1_600_000, 0.15),
    (2_000_000, 0.20),
    (2_400_000, 0.25),
    (None, 0.30),
]

SLABS_OLD = [
    (250_000, 0.00),
    (500_000, 0.05),
    (1_000_000, 0.20),
    (None, 0.30),
]

# The old regime raises the basic exemption with age; the new regime does not.
SLABS_OLD_SENIOR = [          # 60 to 79
    (300_000, 0.00),
    (500_000, 0.05),
    (1_000_000, 0.20),
    (None, 0.30),
]

SLABS_OLD_SUPER_SENIOR = [    # 80 and above
    (500_000, 0.00),
    (1_000_000, 0.20),
    (None, 0.30),
]

SLABS_OLD_BY_AGE = {
    "below_60": SLABS_OLD,
    "senior": SLABS_OLD_SENIOR,
    "super_senior": SLABS_OLD_SUPER_SENIOR,
}

# --- Standard deduction under section 16(ia) ---

STANDARD_DEDUCTION_NEW = 75_000
STANDARD_DEDUCTION_OLD = 50_000

# --- Rebate under section 87A ---

REBATE_87A_NEW = {"income_ceiling": 1_200_000, "max_rebate": 60_000}
REBATE_87A_OLD = {"income_ceiling": 500_000, "max_rebate": 12_500}

# --- Surcharge: (income_above, rate) ---

SURCHARGE_OLD = [(50_00_000, 0.10), (1_00_00_000, 0.15), (2_00_00_000, 0.25), (5_00_00_000, 0.37)]
SURCHARGE_NEW = [(50_00_000, 0.10), (1_00_00_000, 0.15), (2_00_00_000, 0.25)]

CESS_RATE = 0.04

# --- Chapter VI-A ceilings (old regime) ---

CEILING_80C_AGGREGATE = 150_000          # 80C + 80CCC + 80CCD(1) combined
CEILING_80CCD_1B = 50_000
CEILING_80D_SELF = 25_000
CEILING_80D_SELF_SENIOR = 50_000
CEILING_80D_PARENTS = 25_000
CEILING_80D_PARENTS_SENIOR = 50_000
CEILING_80TTA = 10_000
CEILING_80TTB = 50_000

# Sections that survive the section 115BAC(1A) default regime.
VIA_ALLOWED_IN_NEW_REGIME = {"80CCD(2)", "80JJAA"}

# Section 10 exemptions that survive the new regime. HRA under 10(13A) and LTA
# under 10(5) do not, which is why the salary head is recomputed from
# components rather than lifted from Form 16 item 6.
SECTION_10_ALLOWED_IN_NEW_REGIME = {"10(14)(i)"}

# Section 16 deductions other than the standard deduction are unavailable in the
# new regime.
SECTION_16_OTHERS_IN_NEW_REGIME = False

# --------------------------------------------------------------------------
# Capital gains
# --------------------------------------------------------------------------
# The Finance (No. 2) Act 2024 changed capital-gains taxation with effect from
# 23 July 2024. FY 2025-26 falls entirely after that date, so only the post
# rules apply to this year -- but the boundary is kept in code because prior
# years are still re-filed and revised, and because an amount is only correct
# once you can say which side of it a transfer fell.
CG_CHANGEOVER = "2024-07-23"

# Holding period beyond which a gain is long-term, by asset class (months).
HOLDING_PERIOD_MONTHS = {
    "equity_stt": 12,
    "equity_unlisted": 24,
    "bonds_debentures": 12,
    "immovable_property": 24,
    "gold_jewellery": 24,
    "foreign_shares": 24,
    "debt_mf_other": 24,
    "other": 24,
}

# Specified mutual funds under section 50AA are short-term however long they are
# held, so no holding period can make them long-term.
ALWAYS_SHORT_TERM = {"debt_mf_specified"}

CG_RATES = {
    # Listed equity and equity-oriented funds with STT paid.
    "equity_stt": {
        "short": {"section": "111A", "rate": 0.20},
        "long": {"section": "112A", "rate": 0.125,
                 "exemption": 125_000, "grandfathered": True},
    },
    # Everything else long-term: 12.5% without indexation.
    "default": {
        "short": {"section": "slab", "rate": None},   # taxed at slab rates
        "long": {"section": "112", "rate": 0.125},
    },
}

# Section 112A's exemption applies once across all 112A gains, not per row.
EXEMPTION_112A = 125_000

# Short-term capital losses set off against any capital gain; long-term losses
# only against long-term gains. Both carry forward eight years.
CG_CARRY_FORWARD_YEARS = 8
