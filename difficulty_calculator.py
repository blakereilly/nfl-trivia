import pandas as pd
import numpy as np
import os
import argparse

# --- CONFIGURATION ---
CONFIG = {
    'weights': {
        'performance': 0, 
        'longevity': 0.15,
        'recency': 0.30,
        'star_power': 0.55   
    },
    'multipliers': {
        'QB': 1.0,#0.85
        'RB': 1.0,
        'WR': 1.0,
        'TE': 1.15
    },
    'max_rank_cap': 100,
    'good_season_rank_threshold': 24,
    # --- MODIFIED Star Score Settings ---
    'star_tiers': {
        'legendary': {'ranks': range(1, 2), 'points': 15}, # NEW: Rank 1
        'elite':     {'ranks': range(2, 4), 'points': 10}, # UPDATED: Ranks 2-3
        'great':     {'ranks': range(4, 13), 'points': 5},
        'good':      {'ranks': range(13, 25), 'points': 2}
    }
}
# ---------------------

def calculate_component_scores(player_group, global_stats):
    """
    Calculates the individual, unweighted components of the difficulty score.
    """
    # 1. Performance Score (Median Rank)
    median_rank = player_group['PPR_Rank_by_Pos'].median()
    capped_rank = min(median_rank, CONFIG['max_rank_cap'])
    perf_score = (capped_rank - 1) / (CONFIG['max_rank_cap'] - 1)

    # 2. Longevity Score
    num_seasons = player_group['Year'].nunique()
    longevity_score = (global_stats['max_seasons'] - num_seasons) / (global_stats['max_seasons'] - global_stats['min_seasons'])
    
    # 3. Recency Score
    good_seasons = player_group[player_group['PPR_Rank_by_Pos'] <= CONFIG['good_season_rank_threshold']]
    last_relevant_season = good_seasons['Year'].max() if not good_seasons.empty else player_group['Year'].max()
    recency_score = (global_stats['max_year'] - last_relevant_season) / (global_stats['max_year'] - global_stats['min_year'])

    # 4. Star Score (Points-based)
    total_star_points = 0
    # --- MODIFIED LOGIC ---
    # Added a check for the new 'legendary' tier
    for rank in player_group['PPR_Rank_by_Pos']:
        if rank in CONFIG['star_tiers']['legendary']['ranks']:
            total_star_points += CONFIG['star_tiers']['legendary']['points']
        elif rank in CONFIG['star_tiers']['elite']['ranks']:
            total_star_points += CONFIG['star_tiers']['elite']['points']
        elif rank in CONFIG['star_tiers']['great']['ranks']:
            total_star_points += CONFIG['star_tiers']['great']['points']
        elif rank in CONFIG['star_tiers']['good']['ranks']:
            total_star_points += CONFIG['star_tiers']['good']['points']
    # --- END MODIFIED LOGIC ---
            
    avg_points_per_season = total_star_points / num_seasons if num_seasons > 0 else 0

    return pd.Series({
        'perf_score': perf_score,
        'longevity_score': longevity_score,
        'recency_score': recency_score,
        'star_points': avg_points_per_season, 
        'position': player_group['FantPos'].iloc[0]
    })

def main(args):
    """Main function to load data, calculate scores, and display results."""
    base_dir = os.path.dirname(__file__)
    data_path = os.path.join(base_dir, 'stats', 'combined_stats.csv')

    if not os.path.exists(data_path):
        print(f"Error: Cannot find data file at {data_path}")
        return

    df = pd.read_csv(data_path)
    
    player_first_year = df.groupby('Player')['Year'].min().reset_index()
    player_first_year.rename(columns={'Year': 'FirstYear'}, inplace=True)
    df = pd.merge(df, player_first_year, on='Player')
    df = df[df['FirstYear'] >= 2011].copy()
    
    top_24_seasons = df[df['PPR_Rank_by_Pos'] <= 24]
    players_with_2_top_24_seasons = top_24_seasons['Player'].value_counts()
    valid_players_24 = players_with_2_top_24_seasons[players_with_2_top_24_seasons >= 2].index.tolist()
    top_12_seasons = df[df['PPR_Rank_by_Pos'] <= 12]
    valid_players_12 = top_12_seasons['Player'].unique().tolist()
    eligible_players_list = list(set(valid_players_24 + valid_players_12))
    
    full_df = df.copy() 
    df = df[df['Player'].isin(eligible_players_list)].copy()

    if df.empty:
        print("No eligible players found after filtering. Cannot calculate ratings.")
        return
        
    player_seasons = df.groupby('Player')['Year'].nunique()
    global_stats = {
        'min_seasons': player_seasons.min(), 'max_seasons': player_seasons.max(),
        'min_year': df['Year'].min(), 'max_year': df['Year'].max()
    }

    player_groups = df.groupby('Player')
    component_scores = player_groups.apply(calculate_component_scores, global_stats)

    max_star_points = component_scores['star_points'].max()
    component_scores['star_score'] = 1 - (component_scores['star_points'] / max_star_points)

    w = CONFIG['weights']
    raw_scores = (
        w['performance'] * component_scores['perf_score'] +
        w['longevity'] * component_scores['longevity_score'] +
        w['recency'] * component_scores['recency_score'] +
        w['star_power'] * component_scores['star_score']
    )
    
    pos_multipliers = component_scores['position'].map(CONFIG['multipliers']).fillna(1.0)
    raw_scores *= pos_multipliers

    min_raw_score = raw_scores.min()
    max_raw_score = raw_scores.max()
    difficulty_ratings = 1 + 9 * (raw_scores - min_raw_score) / (max_raw_score - min_raw_score)
    difficulty_ratings = difficulty_ratings.round(1)
    
    results_df = difficulty_ratings.reset_index(name='Difficulty')
    pos_df = df[['Player', 'FantPos']].drop_duplicates(subset='Player')
    results_df = pd.merge(results_df, pos_df, on='Player')

    if args.player:
        player_name = args.player
        player_data = results_df[results_df['Player'].str.lower() == player_name.lower()]
        
        if player_data.empty:
            print(f"Error: Player '{player_name}' not found or is not an eligible player for the game.")
            return

        rating = player_data.iloc[0]['Difficulty']
        print(f"\n--- Stats for {player_data.iloc[0]['Player']} ---")
        print(f"Calculated Difficulty: {rating}")
        
        player_stats_full = full_df[full_df['Player'].str.lower() == player_name.lower()].sort_values(by='Year', ascending=False)
        position = player_stats_full['FantPos'].iloc[0]
        base_cols = ['Year', 'G', 'PPR_Rank_by_Pos', 'PPR']
        if position == 'QB':
            position_cols = ['PassYds', 'PassTD', 'RushYds', 'RushTD']
        else:
            position_cols = ['RushYds', 'RushTD', 'Rec', 'RecYds', 'RecTD']
        
        all_desired_cols = base_cols + position_cols
        display_cols = [col for col in all_desired_cols if col in player_stats_full.columns]
        display_stats = player_stats_full[display_cols]
        
        print("\n**Career Stats (Game View):**")
        print(display_stats.to_string(index=False))
    else:
        print("\n--- Player Difficulty Ratings ---")
        print("\n**Top 30 Easiest Players:**")
        print(results_df.sort_values(by='Difficulty', ascending=True).head(150).to_string(index=False))
        
        print("\n**Top 30 Hardest Players:**")
        print(results_df.sort_values(by='Difficulty', ascending=False).head(150).to_string(index=False))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate and display player difficulty ratings.")
    parser.add_argument("-p", "--player", type=str, help="Name of a specific player to look up.")
    args = parser.parse_args()
    main(args)