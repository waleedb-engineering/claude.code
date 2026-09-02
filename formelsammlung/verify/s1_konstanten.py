"""Verifikation Seite 1: Konstanten, Einheiten, abgeleitete Werte."""
import math

k_B = 1.38e-23      # J/K   (Klausurvorgabe)
e   = 1.6e-19       # As    (Klausurvorgabe)
h   = 6.6e-34       # Js    (Klausurvorgabe)
c0  = 3e8           # m/s
T   = 300.0         # K
eps0= 8.854e-12     # As/Vm
n_i = 1.5e10        # cm^-3
Wg_Si_eV = 1.1

rows = []
def chk(name, got, exp, unit, tol=0.02, src=""):
    ok = "OK" if exp is None else ("OK" if abs(got-exp)/abs(exp) <= tol else "ABWEICHUNG")
    rows.append((name, got, exp, unit, ok, src))
    return got

# --- U_T = k_B T / e -------------------------------------------------
UT = k_B*T/e
chk("U_T = k_B*T/e bei T=300K", UT*1e3, 25.0, "mV", 0.05, "Bauplan 8.1.1 Klausurvorgabe 25 mV")
print(f"U_T exakt = {UT*1e3:.4f} mV   (Klausur: 25 mV, Uebungen: 26 mV)")

# --- hbar ------------------------------------------------------------
hbar = h/(2*math.pi)
chk("hbar = h/2pi", hbar, 1.0504e-34, "Js", 0.01, "abgeleitet")

# --- n_i Einheitenumrechnung ----------------------------------------
n_i_m3 = n_i*1e6
chk("n_i cm^-3 -> m^-3 (x1e6)", n_i_m3, 1.5e16, "m^-3", 1e-9, "Bauplan 8.1.1")

# --- mu Einheitenumrechnung -----------------------------------------
mu_n = 0.135                     # m^2/Vs
chk("mu_n m^2/Vs -> cm^2/Vs (x1e4)", mu_n*1e4, 1350, "cm^2/Vs", 1e-9, "Bauplan 6")

# --- lambda_max = h c / W_g (innerer Fotoeffekt Si) -------------------
lam = h*c0/(Wg_Si_eV*e)
chk("lambda_max Si = h*c/W_g", lam*1e6, 1.13, "um", 0.02, "Bauplan 8.2.7")

# --- k_B T in meV ----------------------------------------------------
kT_eV = k_B*T/e
chk("k_B*T bei 300K", kT_eV*1e3, 25.0, "meV", 0.05, "Bauplan 8.1.4 'ca. 25 meV'")

# --- sigma dotiert / undotiert (Bauplan 6) --------------------------
n0_m3 = 5e17*1e6
sig_dot = e*mu_n*n0_m3
chk("sigma dotiert = e*mu_n*n0", sig_dot, 1.08e4, "S/m", 0.01, "Bauplan 6 (korrigierter Wert)")

mu_sum = 0.183
sig_undot = e*mu_sum*n_i_m3
chk("sigma undotiert = e*(mu_n+mu_p)*n_i", sig_undot, 4.39e-4, "S/m", 0.01, "Bauplan 6 / 8.2.2")

chk("Verhaeltnis sigma_dot/sigma_undot", sig_dot/sig_undot, 2.5e7, "-", 0.05, "Bauplan 6 'Faktor ~2,5e7'")

# --- Effektivwert ----------------------------------------------------
chk("sqrt(2)", math.sqrt(2), 1.414, "-", 0.001, "Bauplan 8.1.3")

print()
w = max(len(r[0]) for r in rows)
for name, got, exp, unit, ok, src in rows:
    e_s = "-" if exp is None else f"{exp:.6g}"
    flag = "  <<<" if ok != "OK" else ""
    print(f"{name:<{w}}  Python={got:.6g} {unit:<8} erwartet={e_s:<10} {ok}{flag}")
