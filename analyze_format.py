# -*- coding: utf-8 -*-
"""Analyze the DGT matriculaciones fixed-width format from sample lines."""

mercedes = "030820260        MERCEDES-BENZ                 GLC 300 DE 4MATIC     3W1NKM0KB1S***********401 1993 13.29     0  2885  5    0001ARRECIFE                GCTF10308202635500        ND         B0035004ARRECIFE                       145.00  5   12N                                         861PT1                   CZAL052A                           MERCEDES-BENZ AG                                                      2395    2885M1  AC    0=6EA     2341000PHEV011900                                                                                                                                                                               288816281647M                         N                             03082026"

zontes = "030820260        ZONTES                        703F                  1LD3PWW6A7S***********510  699  6.32   213     0  2    0001TORREJON DE ARDOZ       M M 10308202628850        ND         B0028148TORREJON DE ARDOZ               70.00  2   99N                                         700                      F03                                GUANGDONG TAYO MOTORCYCLE TECHNOLOGY CO., LTD.                        236      425*07 ND    0=5+        00400    000000                                                                                                                                                                               1550   0   00                                                       03082026"

for name, line in [( "mercedes", mercedes), ("zontes", zontes)]:
    print(f"=== {name} === length={len(line)}")
    # print with index markers every 10 chars
    for i in range(0, len(line), 10):
        chunk = line[i:i+10]
        print(f"{i:4d}: {chunk!r}")

# Now let's find known substrings and their positions
print("\n\n=== POSITION SEARCH ===")
def find_all(line, sub):
    res = []
    start = 0
    while True:
        idx = line.find(sub, start)
        if idx == -1:
            break
        res.append(idx)
        start = idx + 1
    return res

for name, line in [("mercedes", mercedes), ("zontes", zontes)]:
    print(f"\n--- {name} ---")
    for sub in ["03082026", "MERCEDES-BENZ", "ZONTES", "GLC", "703F", "ARRECIFE", "TORREJON", "1993", "699", "13.29", "6.32", "2885", "2395", "236", "425", "PHEV", "ND", "M1", "07", "861PT1", "CZAL052A", "F03", "B0035004", "B0028148", "145.00", "70.00"]:
        print(f"  {sub!r}: {find_all(line, sub)}")