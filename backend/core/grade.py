"""
grade.py: every bean labels will be converted to slaty percentage and position against SNI thresholds.
"""
from math import sqrt
 
CLASSES = ("fermented", "under_fermented", "violet", "slaty")
 
#SNI slaty thresholds for mutu I, II, III 
SLATY_MAX = (3.0, 8.0, 20.0)
 
BAND_NAMES = (
    "di bawah ambang slaty Mutu I (maks 3%)",
    "di bawah ambang slaty Mutu II (maks 8%)",
    "di bawah ambang slaty Mutu III (maks 20%)",
    "di atas ambang slaty Mutu III (>20%)",
)
 
LABEL_ID = {
    "fermented": "Fermentasi",
    "under_fermented": "Kurang fermentasi",
    "violet": "Ungu",
    "slaty": "Slaty",
}
 
 
def count_labels(labels):
    """Count beans per class. Unknown labels will be raise (just for safeguard)."""
    counts = {c: 0 for c in CLASSES}
    for i, lab in enumerate(labels):
        if lab not in counts:
            raise ValueError(f"label tidak dikenal pada indeks {i}: {lab!r}")
        counts[lab] += 1
    return counts


def wilson_interval(k, n, z=1.96): #k means slaty beans and n means total number of beans
    """
    Wilson score confidence interval for a proportion. Returns (lo, hi) on a 0 untill 1 scale
    """
    if n <= 0 or not 0 <= k <= n:
        raise ValueError(f"k={k!r} n={n!r} tidak valid")
    z2 = z * z
    denom = n + z2
    #wilson center: k/n pulled toward 0.5, unlike the raw proportion used by wald.
    center = (k + z2 / 2.0) / denom
    #half width of the interval around center.
    half = (z / denom) * sqrt(k * (n - k) / n + z2 / 4.0)
    return max(0.0, center - half), min(1.0, center + half)


def slaty_band(percent):
    """Percentage of slaty compared to SNI threshold. Return index between 0 untill 3."""
    for i, limit in enumerate(SLATY_MAX):
        if percent <= limit:
            return i
    return len(SLATY_MAX)


def grade(labels, n_unreadable=0): 
    """
    labels: labels from classify.py, List of each successfully read bean
    n_unreadable: beans detected but not classified, from segment.py (flagged, dropped_n, and edge_n)
    Returns a dict, not a string. Formatting is in format_report().
    """
    n = len(labels)
    if n == 0:
        raise ValueError(f"tidak ada biji terbaca dari {n_unreadable} terdeteksi")

    counts = count_labels(labels)
    k = counts["slaty"] #k = count of slaty beans
    percent = {c: 100.0 * counts[c] / n for c in CLASSES}
    band = slaty_band(percent["slaty"])

    lo, hi = wilson_interval(k, n)
    ci = (100.0 * lo, 100.0 * hi) #confidence interval for slaty percentage

    #class of unreadable beans (n_unreadable) is unknown, so compute two bounds,  optimistic (all non-slaty), pessimistic (all slaty).
    n_tot = n + n_unreadable
    percent_opt = 100.0 * k / n_tot
    percent_pes = 100.0 * (k + n_unreadable) / n_tot

    #one of the most important 
    ci_conclusif = slaty_band(ci[0]) == slaty_band(ci[1]) #if true then the 95% confidence interval is conclusively in one band, else it crosses a threshold and is inconclusive.
    unread_konklusif = slaty_band(percent_opt) == slaty_band(percent_pes) #if true then the unreadable beans do not change the band, else they could change the band.

    warning = []
    if not ci_conclusif:
        warning.append(
            f"Selang 95% ({ci[0]:.1f}% sampai {ci[1]:.1f}%) melintasi ambang SNI. "
            f"Posisi terhadap ambang belum dapat disimpulkan pada n={n}.")
    if n_unreadable and not unread_konklusif:
        warning.append(
            f"{n_unreadable} biji tidak terbaca. Slaty berada antara {percent_opt:.1f}% dan {percent_pes:.1f}%, "
            f"jatuh di ambang berbeda. Pisahkan bijinya lalu foto ulang.")
    elif n_unreadable:
        warning.append(
            f"{n_unreadable} biji tidak terbaca, tapi tidak mengubah posisi terhadap ambang SNI.")

    return {
        "n_terbaca": n,
        "n_tidak_terbaca": n_unreadable,
        "jumlah": counts,
        "persen": percent,
        "slaty_persen": percent["slaty"],
        "slaty_ci95": ci,
        "slaty_batas_tak_terbaca": (percent_opt, percent_pes),
        "band": band, #could be a code for frontend to show a color or icon
        "band_nama": BAND_NAMES[band],  #showed to the user
        "konklusif": ci_conclusif and unread_konklusif,
        "peringatan": warning,
        "disclaimer": (
            "Indikasi mutu setara SNI 2323:2008, BUKAN sertifikasi. Parameter "
            "lain (berjamur, berserangga, kotoran, berkecambah) belum dinilai."),
    }


def format_report(h): #h is the dict returned by grade()
    """Converting dict from grade() to text. Seperated because we want to test grade() without checking the exact string format."""

    #out is a list of strings, joined with newlines at the end
    out = [f"{h['n_terbaca']} biji dianalisis"]
    if h["n_tidak_terbaca"]: #meaning it is detected but not classified, from segment.py (flagged, dropped_n, and edge_n)
        out.append(f"{h['n_tidak_terbaca']} biji terdeteksi tapi tidak terbaca")
    out.append("")

    for c in ("slaty", "fermented", "violet", "under_fermented"):
        out.append(f"{LABEL_ID[c]:<18} {h['persen'][c]:5.1f}%") #percent is a dict, [c] is the percentage of that class
    lo95, hi95 = h["slaty_ci95"]
    out += [f"Slaty {h['slaty_persen']:.1f}% (selang 95%: {lo95:.1f}% sampai {hi95:.1f}%)",
            h["band_nama"]]
    
    if h["peringatan"]:
        out.append("")
        out += ["PERINGATAN: " + p for p in h["peringatan"]]
    out += ["", h["disclaimer"]]
    return "\n".join(out)


if __name__ == "__main__":
    lo, hi = wilson_interval(0, 20)
    assert lo == 0.0 and 0.15 < hi < 0.17
    print(f"test 1 works (k=0 n=20) : ({lo:.3f}, {hi:.3f}), bukan (0, 0)")

    h = grade(["slaty"] * 6 + ["fermented"] * 71 + ["violet"] * 18
              + ["under_fermented"] * 5)
    assert not h["konklusif"]
    print(f"test 2 works (6% dari n=100) : interval {h['slaty_ci95'][0]:.1f}-{h['slaty_ci95'][1]:.1f}%, tidak konklusif")

    h2 = grade(["slaty"] + ["fermented"] * 19, n_unreadable=5)
    assert not h2["konklusif"]
    print(f"test 3 works (5 tak terbaca) : slaty {h2['slaty_batas_tak_terbaca'][0]:.1f}% sampai {h2['slaty_batas_tak_terbaca'][1]:.1f}%, beda band")

    #check the labels checker
    try:
        count_labels(["fermented", "white"])
        raise AssertionError("seharusnya melempar ValueError")
    except ValueError:
        print("test 4 works (label tak dikenal) : label ditolak")

    print()
    print(format_report(h))