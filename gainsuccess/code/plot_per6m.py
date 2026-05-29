import pandas as pd
import matplotlib.pyplot as plt
import os

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(BASE_DIR, 'output', 'trial10_full_decile_per6m.csv')
IMG_PATH = os.path.join(BASE_DIR, 'output', 'per6m_histogram.png')

def main():
    if not os.path.exists(CSV_PATH):
        print(f"Error: {CSV_PATH} not found.")
        return

    # Load data
    df = pd.read_csv(CSV_PATH, sep=';', decimal=',')
    
    # Plot Success Rate by Decile
    plt.figure(figsize=(10, 6))
    
    # Convert success_rate to percentage
    rates = df['success_rate'] * 100
    labels = df['decile']
    
    colors = plt.cm.RdYlGn(rates / rates.max())
    bars = plt.bar(labels, rates, color=colors, edgecolor='black', alpha=0.8)
    
    plt.axhline(y=rates.mean(), color='red', linestyle='--', label=f'Average ({rates.mean():.1f}%)')
    
    plt.title('per6m Success Rate by Decile (Gain > 10%)', fontsize=14)
    plt.xlabel('Decile (D1=Highest Indicator Value, D10=Lowest)', fontsize=12)
    plt.ylabel('Success Rate (%)', fontsize=12)
    plt.ylim(0, max(rates) * 1.15)
    plt.grid(axis='y', linestyle=':', alpha=0.7)
    plt.legend()

    # Add text labels on top of bars
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                 f'{height:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')

    plt.tight_layout()
    plt.savefig(IMG_PATH, dpi=150)
    print(f"Histogram saved to {IMG_PATH}")

if __name__ == "__main__":
    main()
