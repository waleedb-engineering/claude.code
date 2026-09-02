"""Welcher U_T-Wert steckt in den Musterloesungswerten des Bauplans?"""
import math
n_i = 1.5e10  # cm^-3

def fermi(n0, kT_eV): return kT_eV*math.log(n0/n_i)
def UD(NA, ND, kT_eV): return kT_eV*math.log(NA*ND/n_i**2)

print("Bauplan 8.2.1:  W_F - W_i = 0,45 eV  bei n0 = 5e17 cm^-3")
for lbl, kT in [("25,0 meV (Klausurvorgabe)",0.025),
                ("25,875 meV (k_B*T/e exakt)",0.025875),
                ("26,0 meV (Uebungen)",0.026)]:
    print(f"   kT = {lbl:<28} -> {fermi(5e17,kT):.4f} eV")

print()
print("Bauplan 8.2.4:  U_D = 575 mV  bei N_A = N_D = 1e15 cm^-3")
for lbl, kT in [("25,0 mV",0.025),("25,875 mV",0.025875),("26,0 mV",0.026)]:
    print(f"   U_T = {lbl:<28} -> {UD(1e15,1e15,kT)*1e3:.1f} mV")

print()
print("Bauplan 8.2.1 exakter n0:  n0 = N_D - N_A = 5e17 - 5e15 = %.3e cm^-3" % (5e17-5e15))
print("   p0 = n_i^2/n0 (mit n0=5e17)   = %.4g cm^-3" % (n_i**2/5e17))
print("   p0 = n_i^2/n0 (mit n0=4,95e17)= %.4g cm^-3" % (n_i**2/4.95e17))
