import pandas as pd
import os

csv_path = '/home/sm/potentials/gainsuccess/output/trial11_cross_deciles.csv'

def df_to_markdown(df):
    headers = list(df.columns)
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for _, row in df.iterrows():
        md += "| " + " | ".join([str(val) for val in row.values]) + " |\n"
    return md

def main():
    if not os.path.exists(csv_path): return
    df = pd.read_csv(csv_path, sep=';', decimal=',')
    df['upperLimit'] = df['upperLimit'].round(2)
    df['lowerLimit'] = df['lowerLimit'].round(2)
    md = df_to_markdown(df)
    with open('/home/sm/potentials/gainsuccess/matrix_md.txt', 'w') as f:
        f.write(md)

if __name__ == "__main__":
    main()
