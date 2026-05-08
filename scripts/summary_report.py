import pandas as pd

def generate_report(input_csv, top_n=10):
    df = pd.read_csv(input_csv)
    
    # Calculate a combined efficiency score (average of both if available)
    # If one is missing, it will use the available one (but our filter required both)
    df['Avg_Efficiency'] = (df['6NJS_efficiency'] + df['5TBM_efficiency']) / 2
    
    # Sort by average efficiency
    top_df = df.sort_values(by='Avg_Efficiency', ascending=False).head(top_n)
    
    print(f"\n{'='*90}")
    print(f"{'TOP ' + str(top_n) + ' LIGAND CANDIDATES (Ranked by Combined Efficiency)':^90}")
    print(f"{'='*90}\n")
    
    header = f"{'Ligand ID':<45} | {'6NJS LE':<8} | {'5TBM LE':<8} | {'MW':<6} | {'LogP':<5}"
    print(header)
    print("-" * len(header))
    
    for _, row in top_df.iterrows():
        print(f"{row['ligand:number']:<45} | {row['6NJS_efficiency']:<8.3f} | {row['5TBM_efficiency']:<8.3f} | {row['MW']:<6.1f} | {row['LogP']:<5.2f}")
    
    print(f"\n{'='*90}")
    print(f"Total Filtered Candidates: {len(df)}")
    print(f"Criteria: MW < 400, LogP <= 5, HBD < 3, HBA < 7, PSA < 60, Charge = 0, LE >= 0.3")
    print(f"{'='*90}\n")

if __name__ == "__main__":
    generate_report('data/filtered_ligands.csv')
