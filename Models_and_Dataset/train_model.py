import os
import glob
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, balanced_accuracy_score

# ==========================================
# 1. Directory Pathing
# ==========================================
# Script lives inside Models_and_Dataset/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(SCRIPT_DIR, "Datasets")
MODELS_DIR = os.path.join(SCRIPT_DIR, "Models")

# Auto-create the models directory if missing
os.makedirs(MODELS_DIR, exist_ok=True)
MODEL_OUTPUT_PATH = os.path.join(MODELS_DIR, "rf_drone_model.pkl")

# ==========================================
# 2. Data Loader & Feature Extraction
# ==========================================
def load_datasets():
    csv_paths = glob.glob(os.path.join(DATASETS_DIR, "*.csv"))
    if not csv_paths:
        raise FileNotFoundError(f"[-] No CSV files found in {DATASETS_DIR}")

    df_list = []
    print("[+] Loading CSV datasets:")
    for path in csv_paths:
        file_name = os.path.basename(path)
        df = pd.read_csv(path)
        required_columns = [f'ch_{i}' for i in range(125)] + ['label']
        missing_columns = sorted(set(required_columns) - set(df.columns))
        if missing_columns:
            raise ValueError(f"{file_name} is missing columns: {missing_columns}")
        if not set(df['label'].unique()).issubset({0, 1}):
            raise ValueError(f"{file_name} contains labels outside the binary 0/1 schema")
        df = df.assign(recording_id=file_name)
        print(f"    - {file_name} ({len(df)} frames)")
        df_list.append(df)

    combined_df = pd.concat(df_list, ignore_index=True)
    print(f"[+] Total samples loaded: {len(combined_df)}")
    return combined_df

def extract_rolling_features(df, window_size=5):
    """Computes temporal rolling features across consecutive scan frames."""
    channels = [f'ch_{i}' for i in range(125)]
    X_raw = df[channels].values
    y_raw = df['label'].values

    features, labels = [], []
    for i in range(window_size - 1, len(X_raw)):
        window = X_raw[i-window_size+1:i+1]
        latest = window[-1]

        # RF Spectral Features
        tot_active = np.sum(latest)                           # Overall spectral energy
        mid_upper_hits = np.sum(latest[31:])                   # Out-of-Wi-Fi channel activity
        spectral_delta = np.sum(np.abs(window[-1] - window[-2]))# Channel hopping dynamics
        
        active_indices = np.where(latest == 1)[0]
        dispersion = np.std(active_indices) if len(active_indices) > 0 else 0

        feat_vector = np.hstack([latest, tot_active, mid_upper_hits, spectral_delta, dispersion])
        features.append(feat_vector)
        labels.append(y_raw[i])

    return np.array(features), np.array(labels)

def build_feature_set(df, window_size=5):
    """Extract windows independently per recording; never join two recordings."""
    feature_sets, label_sets, group_sets = [], [], []
    for recording_id, recording in df.groupby('recording_id', sort=True):
        features, labels = extract_rolling_features(recording, window_size)
        feature_sets.append(features)
        label_sets.append(labels)
        group_sets.append(np.full(len(labels), recording_id))
    return np.vstack(feature_sets), np.concatenate(label_sets), np.concatenate(group_sets)

def grouped_split_with_all_classes(X, y, groups, test_size=0.5):
    """Select a grouped holdout containing both labels on each side."""
    for random_state in range(100):
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
        train_indices, test_indices = next(splitter.split(X, y, groups))
        if set(y[train_indices]) == {0, 1} and set(y[test_indices]) == {0, 1}:
            return train_indices, test_indices
    raise ValueError(
        'Could not create a grouped holdout with both classes. '
        'Collect at least two independent recordings per class.'
    )

# ==========================================
# 3. Model Training Pipeline
# ==========================================
def main():
    df_raw = load_datasets()

    print("\n[+] Computing temporal window features (Window Size = 5)...")
    X, y, groups = build_feature_set(df_raw, window_size=5)

    train_indices, test_indices = grouped_split_with_all_classes(X, y, groups)
    X_train, X_test = X[train_indices], X[test_indices]
    y_train, y_test = y[train_indices], y[test_indices]
    train_groups, test_groups = sorted(set(groups[train_indices])), sorted(set(groups[test_indices]))

    print(f"[+] Training Split: {X_train.shape[0]} windows from {train_groups}")
    print(f"[+] Testing Split: {X_test.shape[0]} windows from unseen recordings {test_groups}")
    print("[+] Training Random Forest Classifier...")

    clf = RandomForestClassifier(
        n_estimators=150,
        max_depth=20,
        min_samples_split=4,
        random_state=42,
        n_jobs=-1
    )
    clf.fit(X_train, y_train)

    # Performance Metrics
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)

    print("\n" + "=" * 55)
    print(f" MODEL ACCURACY: {acc * 100:.2f}%")
    print(f" BALANCED ACCURACY: {balanced_accuracy_score(y_test, y_pred) * 100:.2f}%")
    print("=" * 55)
    print("\n--- Classification Report ---")
    print(classification_report(y_test, y_pred, labels=[0, 1], target_names=['Non-Drone (0)', 'Drone Active (1)'], zero_division=0))

    print("--- Confusion Matrix ---")
    print(confusion_matrix(y_test, y_pred))

    # Refit the artifact on every available recording after the honest holdout.
    # The holdout above is for evaluation only; deployment should use all data.
    clf.fit(X, y)

    # Save trained model artifact
    joblib.dump(clf, MODEL_OUTPUT_PATH)
    print(f"\n[SUCCESS] Model saved to: {MODEL_OUTPUT_PATH}\n")

if __name__ == '__main__':
    main()