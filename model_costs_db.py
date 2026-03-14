#!/usr/bin/env python3
"""
model_costs.csvをSQLiteデータベースとして管理するユーティリティ
"""
import sqlite3
import csv
from datetime import datetime
from typing import Optional

# matplotlibのインポート（オプション）
try:
    import matplotlib
    matplotlib.use('TkAgg')  # Windows環境用のバックエンド
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif'] = ['MS Gothic', 'Yu Gothic', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("[注意] matplotlibがインストールされていません。グラフ表示機能は利用できません。")
    print("       インストール方法: pip install matplotlib")

class ModelCostsDB:
    def __init__(self, db_path='model_costs.db', csv_path='model_costs.csv'):
        self.db_path = db_path
        self.csv_path = csv_path
        self.conn = None
        
    def __enter__(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()
    
    def init_db(self):
        """データベースの初期化"""
        cursor = self.conn.cursor()
        
        # モデルコストテーブル
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_updated TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_cost_per_1k_tokens REAL NOT NULL,
                output_cost_per_1k_tokens REAL NOT NULL,
                currency TEXT DEFAULT 'USD',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, model, date_updated)
            )
        ''')
        
        # インデックス作成
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_provider ON model_costs(provider)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_model ON model_costs(model)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON model_costs(date_updated)')
        
        self.conn.commit()
    
    def load_from_csv(self, overwrite=False):
        """CSVからデータをロード"""
        if overwrite:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM model_costs')
            
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                if row['model']:  # 空行をスキップ
                    self.conn.execute('''
                        INSERT OR REPLACE INTO model_costs 
                        (date_updated, provider, model, input_cost_per_1k_tokens, 
                         output_cost_per_1k_tokens, currency, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row['date_updated'],
                        row['provider'],
                        row['model'],
                        float(row['input_cost_per_1k_tokens']),
                        float(row['output_cost_per_1k_tokens']),
                        row.get('currency', 'USD'),
                        row.get('notes', '')
                    ))
                    count += 1
        
        self.conn.commit()
        print(f"[OK] {self.csv_path}から{count}行のデータをロードしました")
    
    def load_multiple_csv(self, csv_files, overwrite=False):
        """複数のCSVファイルからデータをロード"""
        if overwrite:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM model_costs')
        
        total_count = 0
        for csv_file in csv_files:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    if row['model']:  # 空行をスキップ
                        self.conn.execute('''
                            INSERT OR REPLACE INTO model_costs 
                            (date_updated, provider, model, input_cost_per_1k_tokens, 
                             output_cost_per_1k_tokens, currency, notes)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            row['date_updated'],
                            row['provider'],
                            row['model'],
                            float(row['input_cost_per_1k_tokens']),
                            float(row['output_cost_per_1k_tokens']),
                            row.get('currency', 'USD'),
                            row.get('notes', '')
                        ))
                        count += 1
                total_count += count
                print(f"  - {csv_file}: {count}行")
        
        self.conn.commit()
        print(f"[OK] 合計{total_count}行のデータをロードしました")
    
    def get_model_cost(self, provider: str, model: str, date: Optional[str] = None):
        """特定のモデルのコストを取得"""
        cursor = self.conn.cursor()
        
        if date:
            cursor.execute('''
                SELECT * FROM model_costs 
                WHERE provider = ? AND model = ? AND date_updated = ?
            ''', (provider, model, date))
        else:
            cursor.execute('''
                SELECT * FROM model_costs 
                WHERE provider = ? AND model = ?
                ORDER BY date_updated DESC LIMIT 1
            ''', (provider, model))
        
        return cursor.fetchone()
    
    def search_models(self, query: str):
        """モデル名やプロバイダーで検索"""
        cursor = self.conn.cursor()
        search_term = f'%{query}%'
        cursor.execute('''
            SELECT provider, model, input_cost_per_1k_tokens, 
                   output_cost_per_1k_tokens, date_updated
            FROM model_costs 
            WHERE provider LIKE ? OR model LIKE ?
            ORDER BY provider, model
        ''', (search_term, search_term))
        
        return cursor.fetchall()
    
    def get_cheapest_models(self, limit=10):
        """最も安いモデルを取得（入力+出力の合計コスト）"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT provider, model, 
                   input_cost_per_1k_tokens, 
                   output_cost_per_1k_tokens,
                   (input_cost_per_1k_tokens + output_cost_per_1k_tokens) as total_cost,
                   date_updated
            FROM model_costs 
            WHERE date_updated = (SELECT MAX(date_updated) FROM model_costs)
            ORDER BY total_cost ASC
            LIMIT ?
        ''', (limit,))
        
        return cursor.fetchall()
    
    def get_by_provider(self, provider: str):
        """プロバイダー別にモデルを取得"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT model, input_cost_per_1k_tokens, output_cost_per_1k_tokens,
                   date_updated, notes
            FROM model_costs 
            WHERE provider = ?
            ORDER BY date_updated DESC, model
        ''', (provider,))
        
        return cursor.fetchall()
    
    def compare_providers(self):
        """プロバイダー別の平均コストを比較"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT provider,
                   COUNT(*) as model_count,
                   AVG(input_cost_per_1k_tokens) as avg_input_cost,
                   AVG(output_cost_per_1k_tokens) as avg_output_cost,
                   MIN(input_cost_per_1k_tokens + output_cost_per_1k_tokens) as min_total_cost,
                   MAX(input_cost_per_1k_tokens + output_cost_per_1k_tokens) as max_total_cost
            FROM model_costs
            WHERE date_updated = (SELECT MAX(date_updated) FROM model_costs)
            GROUP BY provider
            ORDER BY avg_input_cost + avg_output_cost
        ''')
        
        return cursor.fetchall()
    
    def get_price_history(self, provider: str, model: str):
        """特定モデルの価格履歴を取得"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT date_updated, input_cost_per_1k_tokens, output_cost_per_1k_tokens
            FROM model_costs
            WHERE provider = ? AND model = ?
            ORDER BY date_updated
        ''', (provider, model))
        
        return cursor.fetchall()


def compare_csv_files(old_csv: str, new_csv: str):
    """2つのCSVファイルを比較"""
    import csv
    
    # 古いCSVを読み込む
    old_data = {}
    with open(old_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['model']:
                key = f"{row['provider']}:{row['model']}"
                old_data[key] = {
                    'input': float(row['input_cost_per_1k_tokens']),
                    'output': float(row['output_cost_per_1k_tokens']),
                    'date': row['date_updated'],
                    'notes': row.get('notes', '')
                }
    
    # 新しいCSVを読み込む
    new_data = {}
    with open(new_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['model']:
                key = f"{row['provider']}:{row['model']}"
                new_data[key] = {
                    'input': float(row['input_cost_per_1k_tokens']),
                    'output': float(row['output_cost_per_1k_tokens']),
                    'date': row['date_updated'],
                    'notes': row.get('notes', '')
                }
    
    # 変更されたモデル
    changed = []
    for key in sorted(new_data.keys()):
        if key in old_data:
            old = old_data[key]
            new = new_data[key]
            if old['input'] != new['input'] or old['output'] != new['output']:
                provider, model = key.split(':', 1)
                changed.append({
                    'provider': provider,
                    'model': model,
                    'old_input': old['input'],
                    'new_input': new['input'],
                    'old_output': old['output'],
                    'new_output': new['output'],
                    'old_date': old['date'],
                    'new_date': new['date']
                })
    
    # 新規追加されたモデル
    added = []
    for key in sorted(new_data.keys()):
        if key not in old_data:
            provider, model = key.split(':', 1)
            new = new_data[key]
            added.append({
                'provider': provider,
                'model': model,
                'input': new['input'],
                'output': new['output'],
                'date': new['date']
            })
    
    # 削除されたモデル
    removed = []
    for key in sorted(old_data.keys()):
        if key not in new_data:
            provider, model = key.split(':', 1)
            old = old_data[key]
            removed.append({
                'provider': provider,
                'model': model,
                'input': old['input'],
                'output': old['output'],
                'date': old['date']
            })
    
    return {
        'changed': changed,
        'added': added,
        'removed': removed,
        'old_count': len(old_data),
        'new_count': len(new_data)
    }


def plot_price_changes(result, output_file='price_changes.png'):
    """価格変動をグラフ表示"""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    if not result['changed']:
        print("\n価格変更があったモデルはありません。")
        return
    
    # データ準備
    models = []
    old_costs = []
    new_costs = []
    changes = []
    
    for item in result['changed']:
        old_total = item['old_input'] + item['old_output']
        new_total = item['new_input'] + item['new_output']
        
        model_label = f"{item['provider']}\n{item['model'][:30]}"
        models.append(model_label)
        old_costs.append(old_total)
        new_costs.append(new_total)
        
        if old_total != 0:
            change_pct = ((new_total - old_total) / old_total * 100)
        else:
            change_pct = 100 if new_total > 0 else 0
        changes.append(change_pct)
    
    # 図を作成（2行2列）
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('モデルコスト価格変動分析', fontsize=16, fontweight='bold')
    
    # グラフ1: 旧価格 vs 新価格（棒グラフ）
    x = range(len(models))
    width = 0.35
    
    ax1.bar([i - width/2 for i in x], old_costs, width, label='変更前', alpha=0.8, color='steelblue')
    ax1.bar([i + width/2 for i in x], new_costs, width, label='変更後', alpha=0.8, color='coral')
    ax1.set_xlabel('モデル')
    ax1.set_ylabel('コスト (USD/1000トークン)')
    ax1.set_title('価格変更の比較')
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, rotation=45, ha='right', fontsize=8)
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # グラフ2: 変動率（横棒グラフ）
    colors = ['red' if c > 0 else 'green' for c in changes]
    ax2.barh(models, changes, color=colors, alpha=0.7)
    ax2.set_xlabel('変動率 (%)')
    ax2.set_title('価格変動率')
    ax2.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    ax2.grid(axis='x', alpha=0.3)
    
    # グラフ3: 入力 vs 出力コストの変化（散布図）
    for item in result['changed']:
        # 変更前
        ax3.scatter(item['old_input'], item['old_output'], 
                   s=100, alpha=0.6, color='steelblue', marker='o')
        # 変更後
        ax3.scatter(item['new_input'], item['new_output'], 
                   s=100, alpha=0.6, color='coral', marker='^')
        # 矢印で変化を表示
        ax3.annotate('', xy=(item['new_input'], item['new_output']),
                    xytext=(item['old_input'], item['old_output']),
                    arrowprops=dict(arrowstyle='->', color='gray', lw=1, alpha=0.5))
    
    ax3.set_xlabel('入力コスト (USD/1000トークン)')
    ax3.set_ylabel('出力コスト (USD/1000トークン)')
    ax3.set_title('入力 vs 出力コストの変化\n(○=変更前, △=変更後)')
    ax3.grid(alpha=0.3)
    ax3.legend(['変更前', '変更後'], loc='upper left')
    
    # グラフ4: 価格変動額（実額）
    price_diffs = [new_costs[i] - old_costs[i] for i in range(len(models))]
    colors4 = ['red' if d > 0 else 'green' for d in price_diffs]
    ax4.bar(models, price_diffs, color=colors4, alpha=0.7)
    ax4.set_xlabel('モデル')
    ax4.set_ylabel('価格変動額 (USD/1000トークン)')
    ax4.set_title('価格変動の実額')
    ax4.set_xticklabels(models, rotation=45, ha='right', fontsize=8)
    ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax4.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n[グラフを保存しました: {output_file}]")
    plt.show()


def plot_provider_comparison(result, output_file='provider_comparison.png'):
    """プロバイダー別のコスト比較グラフ"""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # 新規追加と変更されたモデルをプロバイダー別に集計
    provider_data = {}
    
    for item in result['added']:
        provider = item['provider']
        if provider not in provider_data:
            provider_data[provider] = {'models': [], 'input': [], 'output': []}
        provider_data[provider]['models'].append(item['model'][:20])
        provider_data[provider]['input'].append(item['input'])
        provider_data[provider]['output'].append(item['output'])
    
    for item in result['changed']:
        provider = item['provider']
        if provider not in provider_data:
            provider_data[provider] = {'models': [], 'input': [], 'output': []}
        provider_data[provider]['models'].append(item['model'][:20])
        provider_data[provider]['input'].append(item['new_input'])
        provider_data[provider]['output'].append(item['new_output'])
    
    if not provider_data:
        print("\nグラフ表示するデータがありません。")
        return
    
    # 図を作成
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle('プロバイダー別コスト比較', fontsize=16, fontweight='bold')
    
    # プロバイダー別の平均コスト
    providers = list(provider_data.keys())
    avg_input = [sum(provider_data[p]['input']) / len(provider_data[p]['input']) for p in providers]
    avg_output = [sum(provider_data[p]['output']) / len(provider_data[p]['output']) for p in providers]
    
    x = range(len(providers))
    width = 0.35
    
    ax1.bar([i - width/2 for i in x], avg_input, width, label='入力', alpha=0.8, color='steelblue')
    ax1.bar([i + width/2 for i in x], avg_output, width, label='出力', alpha=0.8, color='coral')
    ax1.set_xlabel('プロバイダー')
    ax1.set_ylabel('平均コスト (USD/1000トークン)')
    ax1.set_title('プロバイダー別平均コスト')
    ax1.set_xticks(x)
    ax1.set_xticklabels(providers, rotation=45, ha='right')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # プロバイダー別のモデル数
    model_counts = [len(provider_data[p]['models']) for p in providers]
    ax2.bar(providers, model_counts, alpha=0.8, color='mediumseagreen')
    ax2.set_xlabel('プロバイダー')
    ax2.set_ylabel('モデル数')
    ax2.set_title('プロバイダー別モデル数')
    ax2.set_xticklabels(providers, rotation=45, ha='right')
    ax2.grid(axis='y', alpha=0.3)
    
    # 数値をバーの上に表示
    for i, v in enumerate(model_counts):
        ax2.text(i, v + 0.1, str(v), ha='center', va='bottom', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n[グラフを保存しました: {output_file}]")
    plt.show()


def print_price_changes_sorted(result, sort_by='total'):
    """価格変更を変動率でソート表示"""
    if not result['changed']:
        print("\n価格変更があったモデルはありません。")
        return
    
    # 変動率を計算
    changes_with_rate = []
    for item in result['changed']:
        old_total = item['old_input'] + item['old_output']
        new_total = item['new_input'] + item['new_output']
        
        if sort_by == 'total':
            if old_total != 0:
                change_rate = ((new_total - old_total) / old_total * 100)
            else:
                change_rate = float('inf') if new_total > 0 else 0
        elif sort_by == 'input':
            if item['old_input'] != 0:
                change_rate = ((item['new_input'] - item['old_input']) / item['old_input'] * 100)
            else:
                change_rate = float('inf') if item['new_input'] > 0 else 0
        elif sort_by == 'output':
            if item['old_output'] != 0:
                change_rate = ((item['new_output'] - item['old_output']) / item['old_output'] * 100)
            else:
                change_rate = float('inf') if item['new_output'] > 0 else 0
        
        changes_with_rate.append({
            'item': item,
            'change_rate': change_rate,
            'old_total': old_total,
            'new_total': new_total
        })
    
    # 変動率でソート（降順）
    changes_with_rate.sort(key=lambda x: x['change_rate'], reverse=True)
    
    print("\n" + "=" * 120)
    print(f"価格変更があったモデル（{sort_by}コスト変動率順）")
    print("=" * 120)
    print(f"{'順位':>4} {'プロバイダー':15} {'モデル':40} {'変動':>8} {'旧価格':>12} {'新価格':>12}")
    print("-" * 120)
    
    for i, item_data in enumerate(changes_with_rate, 1):
        item = item_data['item']
        change_rate = item_data['change_rate']
        
        if sort_by == 'total':
            old_value = item_data['old_total']
            new_value = item_data['new_total']
        elif sort_by == 'input':
            old_value = item['old_input']
            new_value = item['new_input']
        elif sort_by == 'output':
            old_value = item['old_output']
            new_value = item['new_output']
        
        arrow = '↑' if new_value > old_value else '↓' if new_value < old_value else '='
        
        if change_rate == float('inf'):
            change_str = "NEW"
        elif change_rate == float('-inf'):
            change_str = "FREE"
        else:
            change_str = f"{arrow}{abs(change_rate):6.1f}%"
        
        print(f"{i:4d} {item['provider']:15} {item['model']:40} {change_str:>8} "
              f"${old_value:10.6f} ${new_value:10.6f}")
    
    print("=" * 120)


def main():
    """コマンドラインインターフェース"""
    import sys
    
    # データベース不要のコマンド
    if len(sys.argv) >= 2 and sys.argv[1] == 'price-changes':
        if len(sys.argv) < 4:
            print("使用法: python model_costs_db.py price-changes <old.csv> <new.csv> [sort]")
            print("sortオプション: total (デフォルト), input, output")
            print("例: python model_costs_db.py price-changes model_costs_backup_original_20251127.csv model_costs.csv total")
            return
        
        old_csv = sys.argv[2]
        new_csv = sys.argv[3]
        sort_by = sys.argv[4] if len(sys.argv) > 4 else 'total'
        
        if sort_by not in ['total', 'input', 'output']:
            print(f"不正なソートオプション: {sort_by}")
            print("sortオプション: total, input, output")
            return
        
        result = compare_csv_files(old_csv, new_csv)
        
        print("\n" + "=" * 120)
        print("価格変動分析")
        print("=" * 120)
        print(f"変更前: {old_csv} ({result['old_count']} モデル)")
        print(f"変更後: {new_csv} ({result['new_count']} モデル)")
        print(f"価格変更: {len(result['changed'])} モデル")
        print(f"新規追加: {len(result['added'])} モデル")
        print(f"削除: {len(result['removed'])} モデル")
        print("=" * 120)
        
        if result['changed']:
            print_price_changes_sorted(result, sort_by)
            
            # グラフ表示
            if MATPLOTLIB_AVAILABLE:
                print("\n[グラフを生成中...]")
                plot_price_changes(result, 'price_changes.png')
                plot_provider_comparison(result, 'provider_comparison.png')
        else:
            print("\n価格変更があったモデルはありません。")
        
        return
    
    if len(sys.argv) >= 2 and sys.argv[1] == 'compare-files':
        if len(sys.argv) < 4:
            print("使用法: python model_costs_db.py compare-files <old.csv> <new.csv>")
            print("例: python model_costs_db.py compare-files model_costs_backup_original_20251127.csv model_costs.csv")
            return
        
        old_csv = sys.argv[2]
        new_csv = sys.argv[3]
        
        result = compare_csv_files(old_csv, new_csv)
        
        print("\n" + "=" * 100)
        print("CSVファイル比較")
        print("=" * 100)
        print(f"変更前: {old_csv} ({result['old_count']} モデル)")
        print(f"変更後: {new_csv} ({result['new_count']} モデル)")
        print("=" * 100)
        
        # 価格変更があったモデル
        if result['changed']:
            print("\n[価格変更があったモデル]")
            print("-" * 100)
            for item in result['changed']:
                print(f"\n{item['provider']:15} / {item['model']}")
                
                # 入力コストの変更
                if item['old_input'] != item['new_input']:
                    if item['old_input'] != 0:
                        change_pct = ((item['new_input'] - item['old_input']) / item['old_input'] * 100)
                        arrow = '↑' if item['new_input'] > item['old_input'] else '↓'
                        print(f"  入力: ${item['old_input']:8.6f} -> ${item['new_input']:8.6f} ({arrow} {abs(change_pct):6.1f}%)")
                    else:
                        print(f"  入力: ${item['old_input']:8.6f} -> ${item['new_input']:8.6f}")
                
                # 出力コストの変更
                if item['old_output'] != item['new_output']:
                    if item['old_output'] != 0:
                        change_pct = ((item['new_output'] - item['old_output']) / item['old_output'] * 100)
                        arrow = '↑' if item['new_output'] > item['old_output'] else '↓'
                        print(f"  出力: ${item['old_output']:8.6f} -> ${item['new_output']:8.6f} ({arrow} {abs(change_pct):6.1f}%)")
                    else:
                        print(f"  出力: ${item['old_output']:8.6f} -> ${item['new_output']:8.6f}")
                
                # 合計コストの変更
                old_total = item['old_input'] + item['old_output']
                new_total = item['new_input'] + item['new_output']
                if old_total != 0:
                    total_change_pct = ((new_total - old_total) / old_total * 100)
                    arrow = '↑' if new_total > old_total else '↓'
                    print(f"  合計: ${old_total:8.6f} -> ${new_total:8.6f} ({arrow} {abs(total_change_pct):6.1f}%)")
        else:
            print("\n[価格変更があったモデル]: なし")
        
        # 新規追加されたモデル
        if result['added']:
            print("\n" + "=" * 100)
            print("[新規追加されたモデル]")
            print("-" * 100)
            for item in result['added']:
                print(f"\n{item['provider']:15} / {item['model']}")
                print(f"  入力: ${item['input']:8.6f}")
                print(f"  出力: ${item['output']:8.6f}")
                print(f"  合計: ${item['input'] + item['output']:8.6f}")
        else:
            print("\n[新規追加されたモデル]: なし")
        
        # 削除されたモデル
        if result['removed']:
            print("\n" + "=" * 100)
            print("[削除されたモデル]")
            print("-" * 100)
            for item in result['removed']:
                print(f"\n{item['provider']:15} / {item['model']}")
                print(f"  入力: ${item['input']:8.6f}")
                print(f"  出力: ${item['output']:8.6f}")
        else:
            print("\n[削除されたモデル]: なし")
        
        # 統計サマリー
        print("\n" + "=" * 100)
        print("[統計サマリー]")
        print("-" * 100)
        print(f"変更前のモデル数: {result['old_count']}")
        print(f"変更後のモデル数: {result['new_count']}")
        print(f"価格変更: {len(result['changed'])} モデル")
        print(f"新規追加: {len(result['added'])} モデル")
        print(f"削除: {len(result['removed'])} モデル")
        print("=" * 100)
        
        # 価格変動のソート表示
        if result['changed']:
            print_price_changes_sorted(result, 'total')
            print("\n入力コストの変動でソート:")
            print_price_changes_sorted(result, 'input')
            print("\n出力コストの変動でソート:")
            print_price_changes_sorted(result, 'output')
            
            # グラフ表示
            if MATPLOTLIB_AVAILABLE:
                print("\n[グラフを生成中...]")
                plot_price_changes(result, 'price_changes_full.png')
                plot_provider_comparison(result, 'provider_comparison_full.png')
        
        return
    
    # データベースを使うコマンド
    with ModelCostsDB() as db:
        db.init_db()
        
        if len(sys.argv) < 2:
            print("使用法:")
            print("  python model_costs_db.py load [file1.csv file2.csv ...] - CSVからデータをロード（複数ファイル可）")
            print("  python model_costs_db.py search <query>    - モデルを検索")
            print("  python model_costs_db.py cheapest [N]      - 最安モデルを表示")
            print("  python model_costs_db.py provider <name>   - プロバイダー別表示")
            print("  python model_costs_db.py compare           - プロバイダー比較")
            print("  python model_costs_db.py compare-files <old.csv> <new.csv> - 2つのCSVファイルを比較（グラフ付き）")
            print("  python model_costs_db.py price-changes <old.csv> <new.csv> [sort] - 価格変動を表示（グラフ付き、sort: total/input/output）")
            print("  python model_costs_db.py cost <provider> <model> - 特定モデルのコスト")
            print("  python model_costs_db.py sql <query>       - 直接SQLクエリを実行")
            print("  python model_costs_db.py sql-file <file.sql> - SQLファイルを実行")
            print("  python model_costs_db.py sql-interactive   - インタラクティブSQLモード")
            print("\n  ※ compare-files と price-changes コマンドは自動的にグラフを生成・表示します")
            return
        
        command = sys.argv[1]
        
        if command == 'load':
            # 複数のCSVファイルを指定可能
            if len(sys.argv) > 2:
                csv_files = sys.argv[2:]
                print(f"複数のCSVファイルをロード: {len(csv_files)}ファイル")
                db.load_multiple_csv(csv_files, overwrite=True)
            else:
                db.load_from_csv(overwrite=True)
            
        elif command == 'search':
            if len(sys.argv) < 3:
                print("検索クエリを指定してください")
                return
            query = sys.argv[2]
            results = db.search_models(query)
            print(f"\n検索結果: '{query}'")
            print("=" * 100)
            for row in results:
                print(f"{row['provider']:15} {row['model']:40} "
                      f"入力: ${row['input_cost_per_1k_tokens']:8.6f} "
                      f"出力: ${row['output_cost_per_1k_tokens']:8.6f} "
                      f"({row['date_updated']})")
                      
        elif command == 'cheapest':
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            results = db.get_cheapest_models(limit)
            print(f"\n最も安いモデル TOP {limit}")
            print("=" * 100)
            for i, row in enumerate(results, 1):
                print(f"{i:2}. {row['provider']:15} {row['model']:40} "
                      f"合計: ${row['total_cost']:8.6f} "
                      f"(入力: ${row['input_cost_per_1k_tokens']:8.6f} "
                      f"出力: ${row['output_cost_per_1k_tokens']:8.6f})")
                      
        elif command == 'provider':
            if len(sys.argv) < 3:
                print("プロバイダー名を指定してください")
                return
            provider = sys.argv[2]
            results = db.get_by_provider(provider)
            print(f"\nプロバイダー: {provider}")
            print("=" * 100)
            for row in results:
                print(f"{row['model']:45} "
                      f"入力: ${row['input_cost_per_1k_tokens']:8.6f} "
                      f"出力: ${row['output_cost_per_1k_tokens']:8.6f}")
                if row['notes']:
                    print(f"  備考: {row['notes']}")
                    
        elif command == 'compare':
            results = db.compare_providers()
            print("\nプロバイダー比較")
            print("=" * 120)
            print(f"{'プロバイダー':15} {'モデル数':>8} {'平均入力':>12} {'平均出力':>12} "
                  f"{'最小合計':>12} {'最大合計':>12}")
            print("=" * 120)
            for row in results:
                print(f"{row['provider']:15} {row['model_count']:8d} "
                      f"${row['avg_input_cost']:11.6f} ${row['avg_output_cost']:11.6f} "
                      f"${row['min_total_cost']:11.6f} ${row['max_total_cost']:11.6f}")
                      
        elif command == 'cost':
            if len(sys.argv) < 4:
                print("使用法: python model_costs_db.py cost <provider> <model>")
                return
            provider = sys.argv[2]
            model = sys.argv[3]
            result = db.get_model_cost(provider, model)
            if result:
                print(f"\nモデル: {result['provider']} / {result['model']}")
                print("=" * 80)
                print(f"入力コスト: ${result['input_cost_per_1k_tokens']:.6f} / 1000トークン")
                print(f"出力コスト: ${result['output_cost_per_1k_tokens']:.6f} / 1000トークン")
                print(f"合計: ${result['input_cost_per_1k_tokens'] + result['output_cost_per_1k_tokens']:.6f}")
                print(f"更新日: {result['date_updated']}")
                if result['notes']:
                    print(f"備考: {result['notes']}")
            else:
                print(f"モデルが見つかりません: {provider} / {model}")
        
        elif command == 'sql':
            if len(sys.argv) < 3:
                print("使用法: python model_costs_db.py sql <query>")
                print('例: python model_costs_db.py sql "SELECT * FROM model_costs LIMIT 5"')
                return
            
            query = sys.argv[2]
            cursor = db.conn.cursor()
            
            try:
                cursor.execute(query)
                results = cursor.fetchall()
                
                if results:
                    # カラム名を取得
                    columns = [description[0] for description in cursor.description]
                    
                    # 列幅を動的に計算
                    col_widths = []
                    for i, col in enumerate(columns):
                        # カラム名の長さ
                        max_width = len(col)
                        
                        # データの最大長を計算
                        for row in results:
                            val_len = len(str(row[i]))
                            if val_len > max_width:
                                max_width = val_len
                        
                        # 特定のカラムは最小幅を設定
                        if col == 'model':
                            max_width = max(max_width, 50)  # モデル名は最低50文字
                        elif col == 'notes':
                            max_width = min(max_width, 60)  # 備考は最大60文字
                        else:
                            max_width = min(max_width, 30)  # 他は最大30文字
                        
                        col_widths.append(max_width)
                    
                    # 結果を表示
                    total_width = sum(col_widths) + len(columns) * 3 - 1
                    print("\n" + "=" * total_width)
                    print(f"クエリ結果: {len(results)} 行")
                    print("=" * total_width)
                    
                    # ヘッダー
                    header = " | ".join(f"{col:{col_widths[i]}}" for i, col in enumerate(columns))
                    print(header)
                    print("-" * total_width)
                    
                    # データ
                    for row in results:
                        row_data = " | ".join(f"{str(val)[:col_widths[i]]:{col_widths[i]}}" for i, val in enumerate(row))
                        print(row_data)
                    
                    print("=" * total_width)
                else:
                    print("\n結果: 0行")
                    
            except Exception as e:
                print(f"\nSQLエラー: {e}")
        
        elif command == 'sql-file':
            if len(sys.argv) < 3:
                print("使用法: python model_costs_db.py sql-file <file.sql>")
                return
            
            sql_file = sys.argv[2]
            
            try:
                with open(sql_file, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
                
                # セミコロンで分割して複数のクエリを実行
                queries = [q.strip() for q in sql_content.split(';') if q.strip()]
                
                cursor = db.conn.cursor()
                
                for i, query in enumerate(queries, 1):
                    print(f"\n[クエリ {i}/{len(queries)}]")
                    print("-" * 80)
                    print(query[:100] + "..." if len(query) > 100 else query)
                    print("-" * 80)
                    
                    try:
                        cursor.execute(query)
                        results = cursor.fetchall()
                        
                        if results:
                            columns = [description[0] for description in cursor.description]
                            
                            # 列幅を動的に計算
                            col_widths = []
                            for j, col in enumerate(columns):
                                max_width = len(col)
                                for row in results[:10]:  # 最初の10行のみで計算
                                    val_len = len(str(row[j]))
                                    if val_len > max_width:
                                        max_width = val_len
                                
                                if col == 'model':
                                    max_width = max(max_width, 50)
                                elif col == 'notes':
                                    max_width = min(max_width, 60)
                                else:
                                    max_width = min(max_width, 30)
                                
                                col_widths.append(max_width)
                            
                            total_width = sum(col_widths) + len(columns) * 3 - 1
                            
                            print(f"結果: {len(results)} 行")
                            print("-" * total_width)
                            
                            # ヘッダー
                            header = " | ".join(f"{col:{col_widths[j]}}" for j, col in enumerate(columns))
                            print(header)
                            print("-" * total_width)
                            
                            # データ（最初の10行のみ）
                            for row in results[:10]:
                                row_data = " | ".join(f"{str(val)[:col_widths[j]]:{col_widths[j]}}" for j, val in enumerate(row))
                                print(row_data)
                            
                            if len(results) > 10:
                                print(f"... 他 {len(results) - 10} 行")
                            
                            print("-" * total_width)
                        else:
                            print("結果: 0行（またはクエリが実行されました）")
                            
                    except Exception as e:
                        print(f"エラー: {e}")
                
            except FileNotFoundError:
                print(f"エラー: ファイルが見つかりません: {sql_file}")
            except Exception as e:
                print(f"エラー: {e}")
        
        elif command == 'sql-interactive':
            print("\n" + "=" * 80)
            print("インタラクティブSQLモード")
            print("=" * 80)
            print("SQLクエリを入力してください。")
            print("  - 複数行入力: セミコロン(;)で終わるまで入力を続けます")
            print("  - 終了: 'exit' または 'quit'")
            print("  - クリア: 'clear' で入力をクリア")
            print("  - スキーマ表示: 'schema' でテーブル構造を表示")
            print("使えるテーブル: model_costs")
            print("=" * 80)
            
            cursor = db.conn.cursor()
            
            while True:
                try:
                    # 複数行入力をサポート
                    query_lines = []
                    prompt = "SQL> "
                    
                    while True:
                        line = input(prompt).strip()
                        
                        if line.lower() in ['exit', 'quit']:
                            if query_lines:
                                # 未完了のクエリがある場合はクリア
                                print("未完了のクエリをクリアして終了します。")
                            print("終了します。")
                            return
                        
                        if line.lower() == 'clear':
                            query_lines = []
                            print("入力をクリアしました。")
                            break
                        
                        if line.lower() == 'schema':
                            # テーブル構造を表示
                            schema_cursor = db.conn.cursor()
                            schema_cursor.execute("PRAGMA table_info(model_costs)")
                            schema = schema_cursor.fetchall()
                            print("\n" + "-" * 80)
                            print("model_costs テーブルの構造:")
                            print("-" * 80)
                            print(f"{'カラム名':25} {'型':15} {'NULL許可':10} {'デフォルト':20}")
                            print("-" * 80)
                            for col in schema:
                                col_name = col[1]
                                col_type = col[2]
                                not_null = "NOT NULL" if col[3] else "NULL OK"
                                default = col[4] if col[4] else "-"
                                print(f"{col_name:25} {col_type:15} {not_null:10} {str(default):20}")
                            print("-" * 80)
                            query_lines = []
                            break
                        
                        if line:
                            query_lines.append(line)
                        
                        # セミコロンで終わっているか、または空行でEnterが押された場合
                        if line.endswith(';') or (not line and query_lines):
                            break
                        
                        # 複数行入力中
                        prompt = "  ...> "
                    
                    query = ' '.join(query_lines).strip()
                    
                    if not query:
                        continue
                    
                    cursor.execute(query)
                    results = cursor.fetchall()
                    
                    if results:
                        # カラム名を取得
                        columns = [description[0] for description in cursor.description]
                        
                        # 列幅を動的に計算
                        col_widths = []
                        for i, col in enumerate(columns):
                            max_width = len(col)
                            for row in results[:20]:  # 最初の20行のみで計算
                                val_len = len(str(row[i]))
                                if val_len > max_width:
                                    max_width = val_len
                            
                            if col == 'model':
                                max_width = max(max_width, 50)
                            elif col == 'notes':
                                max_width = min(max_width, 60)
                            else:
                                max_width = min(max_width, 30)
                            
                            col_widths.append(max_width)
                        
                        total_width = sum(col_widths) + len(columns) * 3 - 1
                        
                        # 結果を表示
                        print("\n" + "-" * total_width)
                        print(f"結果: {len(results)} 行")
                        print("-" * total_width)
                        
                        # ヘッダー
                        header = " | ".join(f"{col:{col_widths[i]}}" for i, col in enumerate(columns))
                        print(header)
                        print("-" * total_width)
                        
                        # データ（最初の20行のみ）
                        for row in results[:20]:
                            row_data = " | ".join(f"{str(val)[:col_widths[i]]:{col_widths[i]}}" for i, val in enumerate(row))
                            print(row_data)
                        
                        if len(results) > 20:
                            print(f"... 他 {len(results) - 20} 行")
                        
                        print("-" * total_width)
                    else:
                        print("\n結果: 0行（またはクエリが実行されました）")
                        
                except KeyboardInterrupt:
                    print("\n\n終了します。")
                    break
                except Exception as e:
                    print(f"\nエラー: {e}")
        
        else:
            print(f"不明なコマンド: {command}")


if __name__ == '__main__':
    main()

