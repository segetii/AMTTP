import json
from pathlib import Path

PATH = Path(r"c:\amttp\papers\comprehensive_bsdt_results_strict_transfer.json")

def main() -> None:
    d = json.loads(PATH.read_text(encoding="utf-8"))
    rows = d["rows"]

    transfer_rows = [r for r in rows if str(r[2]).startswith("Transfer-XGB")]
    print(f"Transfer rows: {len(transfer_rows)}")

    for r in transfer_rows:
        ds, domain, model = r[0], r[1], r[2]
        n_total, n_fraud = int(r[3]), int(r[4])

        base_auc, base_f1, base_rec, base_prec, base_fa, base_tp, base_fp = r[5], r[6], r[7], r[8], r[9], int(r[10]), int(r[11])
        corr_f1, corr_rec, corr_prec, corr_fa, corr_tp, corr_fp = r[12], r[13], r[14], r[15], int(r[16]), int(r[17])

        # SignedLR (present in all strict outputs created so far)
        slr_f1, slr_rec, slr_prec, slr_fa, slr_auc, slr_tp, slr_fp = None, None, None, None, None, None, None
        if len(r) >= 25:
            slr_f1, slr_rec, slr_prec, slr_fa, slr_auc, slr_tp, slr_fp = r[18], r[19], r[20], r[21], r[22], int(r[23]), int(r[24])

        # QuadSurf (appended after SignedLR)
        quad = None
        if len(r) >= 33:
            quad = {
                "f1": float(r[25]),
                "rec": float(r[26]),
                "prec": float(r[27]),
                "fa": float(r[28]),
                "auc": float(r[29]),
                "tp": int(r[30]),
                "fp": int(r[31]),
                "alpha": float(r[32]),
            }

        # QuadSurf + ExpGate (sigmoid gate on base probability)
        qexp = None
        if len(r) >= 43:
            qexp = {
                "f1": float(r[33]),
                "rec": float(r[34]),
                "prec": float(r[35]),
                "fa": float(r[36]),
                "auc": float(r[37]),
                "tp": int(r[38]),
                "fp": int(r[39]),
                "alpha": float(r[40]),
                "tau": float(r[41]),
                "k": float(r[42]),
            }

        print(f"\n{ds} ({domain}) / {model}  test_n={n_total} fraud={n_fraud}")
        print(f"  Base:  AUC={base_auc:.3f} F1={base_f1:.3f} Rec={base_rec:.3f} Prec={base_prec:.3f} FA={base_fa:.1%} TP={base_tp} FP={base_fp}")
        print(f"  +MFLS: F1={corr_f1:.3f} Rec={corr_rec:.3f} Prec={corr_prec:.3f} FA={corr_fa:.1%} TP={corr_tp} FP={corr_fp}")

        if slr_f1 is not None:
            print(f"  SignedLR: AUC={slr_auc:.3f} F1={slr_f1:.3f} Rec={slr_rec:.3f} Prec={slr_prec:.3f} FA={slr_fa:.1%} TP={slr_tp} FP={slr_fp}")
        if quad is not None:
            print(
                f"  QuadSurf(a={quad['alpha']:.2g}): AUC={quad['auc']:.3f} F1={quad['f1']:.3f} "
                f"Rec={quad['rec']:.3f} Prec={quad['prec']:.3f} FA={quad['fa']:.1%} TP={quad['tp']} FP={quad['fp']}"
            )
        if qexp is not None:
            print(
                f"  QuadSurf+ExpGate(a={qexp['alpha']:.2g},tau={qexp['tau']:.2g},k={qexp['k']:.0f}): AUC={qexp['auc']:.3f} "
                f"F1={qexp['f1']:.3f} Rec={qexp['rec']:.3f} Prec={qexp['prec']:.3f} FA={qexp['fa']:.1%} TP={qexp['tp']} FP={qexp['fp']}"
            )


if __name__ == "__main__":
    main()
