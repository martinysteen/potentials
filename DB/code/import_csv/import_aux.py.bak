# =============================================================================
# import_aux.py — Import aux_deciles.csv and aux_win-loss.csv
# =============================================================================

import pandas as pd
from pot_import_utils import get_conn, log, upsert

AUX_DECILES  = "/home/sm/potentials/DB_old_corr/repositoryRTBI/Longi/aux_deciles.csv"
AUX_WIN_LOSS = "/home/sm/potentials/DB_old_corr/repositoryRTBI/Longi/aux_win-loss.csv"

def run_deciles(conn):
    log("import_aux_deciles START")

    df = pd.read_csv(AUX_DECILES, sep=';', decimal=',')
    df.columns = ['indicator', 'decile', 'upper_limit', 'lower_limit']
    df = df.where(pd.notna(df), None)

    rows = df.to_dict('records')
    n = upsert(conn, 'aux_deciles', rows,
               conflict_cols=['indicator', 'decile'],
               update_cols=['upper_limit', 'lower_limit'])

    log(f"import_aux_deciles DONE — {n} rows upserted")

def run_win_loss(conn):
    log("import_aux_win_loss START")

    df = pd.read_csv(AUX_WIN_LOSS, sep=';', decimal=',', low_memory=False)

    # Normalise column names
    df.columns = [
        'daynum', 'ticker',
        'pred_label_20d', 'p_win_20d', 'p_loss_20d',
        'pred_label_50d', 'p_win_50d', 'p_loss_50d'
    ]

    df['daynum'] = df['daynum'].astype(int)

    # NoData sentinel values → NULL
    for col in ['pred_label_20d', 'pred_label_50d']:
        df[col] = df[col].replace({'NoData': None, 'NoLoss': 'NoLoss'})

    df = df.where(pd.notna(df), None)

    rows = df.to_dict('records')
    n = upsert(conn, 'aux_win_loss', rows,
               conflict_cols=['daynum', 'ticker'],
               update_cols=['pred_label_20d', 'p_win_20d', 'p_loss_20d',
                            'pred_label_50d', 'p_win_50d', 'p_loss_50d'])

    log(f"import_aux_win_loss DONE — {n} rows upserted")

def run():
    conn = get_conn()
    run_deciles(conn)
    run_win_loss(conn)
    conn.close()

if __name__ == '__main__':
    run()
