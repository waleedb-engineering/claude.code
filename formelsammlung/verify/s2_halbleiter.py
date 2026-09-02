"""Verifikation Seite 2: dotierter Halbleiter, Fermi-Abstand, sigma, pn-Uebergang.
Referenz: Bauplan 8.2 + handschriftliches REZEPT-Blatt (Fotos 1/2)."""
import math

k_B, e, T = 1.38e-23, 1.6e-19, 300.0
n_i  = 1.5e10          # cm^-3
N_D, N_A = 5e17, 5e15  # cm^-3

print("=== Rezept-Schrittkette, Zahlen wie im handschriftlichen Blatt ===")
# Schritt 1: Typ
print(f"1) N_D={N_D:.0e} > N_A={N_A:.0e}  ->  n-Halbleiter")

# Schritt 2: Majoritaeten / Minoritaeten
n0_exakt = N_D - N_A
n0 = 5e17                     # Naeherung der Musterloesung
p0 = n_i**2/n0
print(f"2) n0 exakt = N_D-N_A = {n0_exakt:.3e} cm^-3   -> genaehert {n0:.0e} cm^-3")
print(f"   p0 = n_i^2/n0      = {p0:.4g} cm^-3")

# Schritt 3: Fermi-Abstand in J
kT_J = k_B*T
arg  = n0/n_i
ln   = math.log(arg)
WF_J = kT_J*ln
print(f"3) k_B*T           = {kT_J:.3e} J")
print(f"   n0/n_i          = {arg:.4e}")
print(f"   ln(n0/n_i)      = {ln:.4f}")
print(f"   W_F-W_i         = {WF_J:.4e} J")

# Schritt 4: J -> eV
WF_eV = WF_J/e
print(f"4) W_F-W_i         = {WF_eV:.4f} eV   -> gerundet {round(WF_eV,2)} eV")

# Schritt 5: Banddiagramm-Lagen
Wg = 1.1
print(f"5) W_g={Wg} eV; W_i mittig; W_F liegt {WF_eV:.2f} eV UEBER W_i (n-HL)")
print(f"   Abstand W_C-W_F = {Wg/2-WF_eV:.4f} eV")

print("\n=== Leitfaehigkeit (Bauplan 6, Korrektur 5) ===")
mu_n, mu_sum = 0.135, 0.183
n0_m3, ni_m3 = n0*1e6, n_i*1e6
sig_dot   = e*mu_n*n0_m3
sig_undot = e*mu_sum*ni_m3
print(f"sigma dotiert   = {e:.1e}*{mu_n}*{n0_m3:.1e} = {sig_dot:.4g} S/m")
print(f"sigma undotiert = {e:.1e}*{mu_sum}*{ni_m3:.1e} = {sig_undot:.4g} S/m")
print(f"Verhaeltnis     = {sig_dot/sig_undot:.3e}")

print("\n=== Diffusionsspannung (Bauplan 8.2.4) ===")
for lbl,UT in [("k_B*T/e exakt = 25,875 mV",kT_J/e),("Klausur 25 mV",0.025)]:
    UD = UT*math.log(1e15*1e15/n_i**2)
    print(f"U_D (N_A=N_D=1e15) mit {lbl:<26} = {UD*1e3:.1f} mV")

print("\n=== Photon / Materiewelle (Bauplan 8.2.7) ===")
h, c0 = 6.6e-34, 3e8
print(f"lambda_max(Si) = h*c/W_g = {h*c0/(1.1*e)*1e6:.3f} um")

print("\n=== Abgleich gegen Referenzwerte ===")
ref = [("W_F-W_i [eV]", WF_eV, 0.45, "Bauplan 8.2.1 + Foto"),
       ("k_B*T [J]",    kT_J, 4.14e-21, "Foto Schritt 3"),
       ("ln(n0/n_i)",   ln,   17.322,   "Foto Schritt 3"),
       ("W_F-W_i [J]",  WF_J, 7.17e-20, "Foto Schritt 3"),
       ("p0 [cm^-3]",   p0,   4.5e2,    "Bauplan 6"),
       ("sigma dot [S/m]",   sig_dot,  1.08e4,  "Bauplan 6"),
       ("sigma undot [S/m]", sig_undot,4.39e-4, "Bauplan 6"),
       ("U_D [mV]", (kT_J/e)*math.log(1e30/n_i**2)*1e3, 575, "Bauplan 8.2.4"),
       ("lambda_max [um]", h*c0/(1.1*e)*1e6, 1.13, "Bauplan 8.2.7")]
for name, got, exp, src in ref:
    ok = "OK" if abs(got-exp)/abs(exp) <= 0.01 else "ABWEICHUNG <<<"
    print(f"  {name:<20} Python={got:<12.5g} Referenz={exp:<10.5g} {ok:<16} [{src}]")
