# Chat - 最新版チャットボット（まとめ機能・複数行編集・包括的エラー対応）
# Version: 8.0.0
# Features: 
# - まとめ機能: AIによる会話履歴の要約とファイル保存
# - 複数行入力: 継続的な複数行モードと高度な編集機能
# - 高速モデル対応: --fastスイッチで高速版モデルに切り替え
# - 包括的エラー対応: API制限エラーの自動検出・対応・リトライ
# - トークン節約機能: まとめの履歴除外による長時間会話対応
# - 最新AIモデル: 全プロバイダーの最新モデルに対応

import sys
import os
import csv
import time
import importlib
from datetime import datetime
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder
)
from langchain.schema.runnable import (
    RunnableLambda,
    RunnableSequence,
    RunnablePassthrough
)
from langchain.schema import AIMessage, HumanMessage
import argparse # argparseをインポート

# Version information
VERSION = "8.0.0"
VERSION_DATE = "2025-08-18"

# AI Assistants configuration file
AI_ASSISTANTS_CONFIG_FILE = "ai_assistants_config.csv"

# Logs and summaries directories
LOGS_DIR = "logs"
SUMMARIES_DIR = "summaries"
SESSIONS_DIR = "sessions"  # 統合型用

# ファイル管理モード設定
FILE_ORGANIZATION_MODE = "separated"  # "separated" or "unified"

MAX_HISTORY_LENGTH = 10

# API制限エラー対応の設定
API_ERROR_CODES = {
    '413': 'Request too large',
    '429': 'Rate limit exceeded',
    '503': 'Service unavailable',
    '504': 'Gateway timeout'
}

def detect_api_error(error_str):
    """APIエラーの種類を検出する"""
    error_str_lower = error_str.lower()
    
    # エラーコードを検出
    detected_code = None
    for code in API_ERROR_CODES.keys():
        if code in error_str:
            detected_code = code
            break
    
    # キーワードベースでの検出
    if not detected_code:
        if any(keyword in error_str_lower for keyword in ['rate limit', 'rate_limit', 'too many requests']):
            detected_code = '429'
        elif any(keyword in error_str_lower for keyword in ['request too large', 'payload too large', 'content too long']):
            detected_code = '413'
        elif any(keyword in error_str_lower for keyword in ['service unavailable', 'temporarily unavailable']):
            detected_code = '503'
        elif any(keyword in error_str_lower for keyword in ['timeout', 'gateway timeout']):
            detected_code = '504'
    
    return detected_code

def handle_api_error(error_code, error_str, attempt, max_retries, retry_delay, conversation_history=None):
    """APIエラーに応じた適切な対応を実行する"""
    
    if error_code == '413':  # Request too large
        print(f"🔴 リクエストサイズエラー: {API_ERROR_CODES[error_code]}")
        
        # 会話履歴を自動削減して再試行
        if conversation_history and attempt < max_retries - 1:
            history_size = conversation_history.get_history_size_estimate()
            print(f"� 現在の履歴サイズ: 約{history_size:,}文字")
            
            if conversation_history.reduce_history():
                new_size = conversation_history.get_history_size_estimate()
                print(f"🔧 履歴を自動削減しました: {history_size:,} → {new_size:,}文字")
                print("🔄 削減された履歴で再試行します...")
                return True  # リトライする
        
        print("�💡 対応策:")
        print("   - 入力テキストを短くしてください")
        print("   - 会話履歴をリセットしてください")
        print("   - より大きなコンテキストウィンドウを持つモデルに変更してください")
        return False  # これ以上リトライしない
    
    elif error_code == '429':  # Rate limit exceeded
        if attempt < max_retries - 1:
            wait_time = retry_delay * (2 ** attempt)
            print(f"🟡 レート制限エラー: {API_ERROR_CODES[error_code]}")
            print(f"⏰ {wait_time}秒待機してから再試行します...")
            time.sleep(wait_time)
            return True  # リトライする
        else:
            print(f"🔴 レート制限エラー: 最大リトライ回数に達しました")
            print("💡 対応策:")
            print("   - しばらく時間を置いてから再試行してください")
            print("   - 有料プランにアップグレードを検討してください")
            return False
    
    elif error_code == '503':  # Service unavailable
        if attempt < max_retries - 1:
            wait_time = retry_delay
            print(f"🟡 サービス一時停止: {API_ERROR_CODES[error_code]}")
            print(f"⏰ {wait_time}秒待機してから再試行します...")
            time.sleep(wait_time)
            return True  # リトライする
        else:
            print(f"🔴 サービス停止: 復旧していません")
            print("💡 対応策:")
            print("   - 別のAIプロバイダーに切り替えてください")
            print("   - しばらく時間を置いてから再試行してください")
            return False
    
    elif error_code == '504':  # Gateway timeout
        if attempt < max_retries - 1:
            wait_time = retry_delay // 2  # タイムアウトの場合は短めの待機
            print(f"🟡 タイムアウトエラー: {API_ERROR_CODES[error_code]}")
            print(f"⏰ {wait_time}秒待機してから再試行します...")
            time.sleep(wait_time)
            return True  # リトライする
        else:
            print(f"🔴 タイムアウト: 最大リトライ回数に達しました")
            print("💡 対応策:")
            print("   - ネットワーク接続を確認してください")
            print("   - 入力を短くしてください")
            return False
    
    else:
        # 不明なエラー
        print(f"🔴 不明なAPIエラー: {error_str}")
        return False

def format_error_message(error_code, error_str):
    """エラーメッセージを分かりやすい形式でフォーマットする"""
    error_emojis = {
        '413': '📏',
        '429': '⏱️',
        '503': '🚫',
        '504': '⏰'
    }
    
    emoji = error_emojis.get(error_code, '❌')
    description = API_ERROR_CODES.get(error_code, 'Unknown error')
    
    return f"{emoji} {description}"

def print_version_info():
    """バージョン情報を表示"""
    print(f"🤖 Chat - AI チャットボット v{VERSION} ({VERSION_DATE})")
    print("=" * 60)
    print("✨ 新機能:")
    print("  📋 まとめ機能 - 会話履歴をAIが要約してファイル保存")
    print("  📝 複数行編集 - 高度な行編集機能（もとい/ちゃいちゃい）")
    print("  ⚡ 高速モデル - --fastスイッチで高速版に切り替え")
    print("  � 包括的エラー対応 - API制限エラーの自動検出・対応・リトライ")
    print("  💡 トークン節約機能 - まとめの履歴除外による長時間会話対応")
    print("=" * 60)

class ConversationHistory:
    """会話履歴を管理するクラス"""
    def __init__(self, max_length=10):
        self.max_length = max_length
        self.messages = []
    
    def add_message(self, message):
        """メッセージを追加"""
        self.messages.append(message)
        # 最大長を超えた場合、古いメッセージを削除
        if len(self.messages) > self.max_length * 2:  # User/Assistant ペアで管理
            self.messages = self.messages[-self.max_length * 2:]
    
    def get_messages(self):
        """メッセージリストを取得"""
        return self.messages
    
    def extend_messages(self, messages):
        """複数のメッセージを追加"""
        self.messages.extend(messages)
        # 最大長を超えた場合、古いメッセージを削除
        if len(self.messages) > self.max_length * 2:
            self.messages = self.messages[-self.max_length * 2:]

    def reduce_history(self, reduction_factor=0.5):
        """会話履歴を削減する（413エラー対応）"""
        if len(self.messages) > 2:  # 最低限の履歴は保持
            new_length = max(2, int(len(self.messages) * reduction_factor))
            # 最新のメッセージを優先して保持
            self.messages = self.messages[-new_length:]
            return True
        return False
    
    def get_history_size_estimate(self):
        """会話履歴のおおよそのサイズを推定する（文字数ベース）"""
        total_chars = 0
        for message in self.messages:
            if hasattr(message, 'content'):
                total_chars += len(str(message.content))
        return total_chars

def load_ai_assistants_config():
    """CSVファイルからAI Assistants設定を読み込む"""
    ai_assistants = {}
    
    if not os.path.exists(AI_ASSISTANTS_CONFIG_FILE):
        print(f"[ERROR] AI Assistants設定ファイル '{AI_ASSISTANTS_CONFIG_FILE}' が見つかりません。")
        return ai_assistants
    
    try:
        with open(AI_ASSISTANTS_CONFIG_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                assistant_name = row['assistant_name']
                ai_assistants[assistant_name] = {
                    'module': row['module'],
                    'class': row['class'],
                    'model': row['model'],
                    'fast_model': row.get('fast_model', '').strip()  # 空文字列の場合もある
                }
        print(f"[INFO] AI Assistants設定を {AI_ASSISTANTS_CONFIG_FILE} から読み込みました。")
    except Exception as e:
        print(f"[ERROR] AI Assistants設定ファイルの読み込みに失敗しました: {e}")
        return {}
    
    return ai_assistants

def parse_arguments(ai_assistants):
    parser = argparse.ArgumentParser(
        description="Chat - AI チャットボット（まとめ機能・複数行編集対応）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python Chat.py                           # デフォルト設定で開始
  python Chat.py -a ChatGPT --fast         # ChatGPTの高速版を使用
  python Chat.py -s custom_system.txt      # カスタムシステムメッセージファイルを指定
  python Chat.py --latest                  # 最新のログファイルを自動読み込み
  python Chat.py -l 20250726_130500        # logs/フォルダからファイル名で読み込み
  python Chat.py -l logs/conversation.csv  # フルパスで読み込み
  python Chat.py -l log.csv -a Groq        # ログを読み込むが、Groqに切り替え

ファイル管理:
  ログファイル: logs/ フォルダに自動保存
  まとめファイル: summaries/ フォルダに自動保存
  システムメッセージ: デフォルトは system_message.txt
  --latest: 最新ログファイルを自動選択

モデル継続オプション:
  --confirm-model    : ログ読み込み時に毎回モデル選択を確認
  --ignore-log-model : ログのモデル設定を無視して指定設定を強制使用

特別コマンド:
  'multi' または '複数行'    : 複数行入力モードに切り替え
  'まとめてください'        : 会話履歴をAIがまとめてファイル保存
  'もとい' / 'ちゃいちゃい' : 複数行モードで直前の行を削除
        """
    )
    # システムメッセージファイルの引数（新規追加）
    parser.add_argument("-s", "--system-message", type=str, default="system_message.txt",
                        help="Path to the system message file. Default: system_message.txt")
    # AIアシスタント名の引数 (デフォルト: Groq)
    parser.add_argument("-a", "--assistant", type=str, default="Groq", choices=ai_assistants.keys(),
                        help=f"Specify the AI assistant to use. Choices: {list(ai_assistants.keys())}")
    # モデル名の引数 (デフォルトは選択されたアシスタントに依存)
    parser.add_argument("-m", "--model", type=str,
                        help="Specify the model name. If not provided, uses the default for the chosen assistant.")
    # 読み込むログファイルの引数
    parser.add_argument("-l", "--load-log", type=str, default=None,
                        help="Path to the CSV conversation log file to load and continue. Can specify just filename (searches in logs/ folder) or full path.")
    # 最新ログを自動読み込み
    parser.add_argument("--latest", action="store_true",
                        help="Load the latest log file from logs folder automatically")
    # 高速版モデルを使用するスイッチ
    parser.add_argument("--fast", action="store_true",
                        help="Use fast version of the selected assistant (e.g., Groq -> GroqFast)")
    # ログ継続時のモデル選択確認
    parser.add_argument("--confirm-model", action="store_true",
                        help="Confirm model selection when loading from log file")
    # ファイル管理モード
    parser.add_argument("--unified", action="store_true",
                        help="Use unified file organization (logs and summaries in same session folder)")
    # ログのモデル設定を無視して強制的に指定設定を使用
    parser.add_argument("--ignore-log-model", action="store_true",
                        help="Ignore model settings from log file and use specified settings")
    # バージョン表示
    parser.add_argument("--version", action="version", version=f"Chat v{VERSION}")

    args = parser.parse_args()

    # --fast スイッチが指定された場合、高速版モデルに切り替え
    if args.fast:
        fast_model = ai_assistants[args.assistant].get('fast_model', '').strip()
        if fast_model:
            print(f"[INFO] --fast スイッチにより {ai_assistants[args.assistant]['model']} から {fast_model} に切り替えます。")
            # モデル名を直接変更（アシスタント名は変更しない）
            ai_assistants[args.assistant]['model'] = fast_model
        else:
            print(f"[WARNING] {args.assistant} には高速版がありません。通常版 {ai_assistants[args.assistant]['model']} を使用します。")

    # モデル名が指定されていない場合、アシスタントのデフォルトモデルを使用
    if args.model is None:
        args.model = ai_assistants[args.assistant]['model']

    return args

def find_latest_log():
    """logsフォルダから最新のログファイルを検索"""
    if not os.path.exists(LOGS_DIR):
        return None
    
    log_files = [f for f in os.listdir(LOGS_DIR) if f.endswith('.csv')]
    if not log_files:
        return None
    
    # ファイル名でソート（タイムスタンプ形式なので文字列ソートで時系列順になる）
    log_files.sort(reverse=True)
    latest_log = os.path.join(LOGS_DIR, log_files[0])
    return latest_log

def resolve_log_path(log_path):
    """ログファイルパスを解決（ファイル名のみの場合はlogsフォルダを検索）"""
    if log_path is None:
        return None
    
    # フルパスまたは相対パスが指定された場合
    if os.path.sep in log_path or log_path.endswith('.csv'):
        if os.path.exists(log_path):
            return log_path
        # logsフォルダ内も確認
        logs_path = os.path.join(LOGS_DIR, os.path.basename(log_path))
        if os.path.exists(logs_path):
            return logs_path
    
    # ファイル名のみの場合、logsフォルダ内を検索
    if not log_path.endswith('.csv'):
        log_path += '.csv'
    
    logs_path = os.path.join(LOGS_DIR, log_path)
    if os.path.exists(logs_path):
        return logs_path
    
    return log_path  # 元のパスを返す（エラーは呼び出し側で処理）

# CSVから履歴と最後の設定を読み込む関数
def load_history_from_csv(filepath):
    messages = []
    last_turn_id = 0
    last_ai_assistant = None
    last_model_name = None

    if not os.path.exists(filepath):
        print(f"[WARNING] 指定されたログファイルが見つかりません: {filepath}")
        return messages, last_turn_id, last_ai_assistant, last_model_name

    try:
        with open(filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            try:
                turn_id_index = header.index('TurnID')
                speaker_index = header.index('Speaker')
                content_index = header.index('Content')
                ai_assistant_index = header.index('AI_Assistant')
                model_name_index = header.index('ModelName')
                # IsSummary列の確認（古いログファイルとの互換性のため）
                is_summary_index = None
                try:
                    is_summary_index = header.index('IsSummary')
                except ValueError:
                    # IsSummary列がない古いログファイルの場合
                    pass
            except ValueError as e:
                print(f"[ERROR] ログファイルのヘッダーが不正です: {e}. 必要な列: TurnID, Speaker, Content, AI_Assistant, ModelName")
                return [], 0, None, None

            current_last_assistant = None
            current_last_model = None
            current_last_id = 0

            for row in reader:
                try:
                    turn_id = int(row[turn_id_index])
                    speaker = row[speaker_index]
                    content = row[content_index]
                    
                    # まとめエントリを除外する
                    is_summary = False
                    if is_summary_index is not None and len(row) > is_summary_index:
                        is_summary = row[is_summary_index].lower() == 'true'
                    
                    if is_summary:
                        print(f"[INFO] まとめエントリをスキップしました: TurnID {turn_id}")
                        continue  # まとめエントリは会話履歴に含めない
                    
                    if speaker == 'Assistant':
                        # 空でない場合に更新する
                        assistant_in_row = row[ai_assistant_index]
                        model_in_row = row[model_name_index]
                        if assistant_in_row:
                             current_last_assistant = assistant_in_row
                        if model_in_row:
                             current_last_model = model_in_row

                    if speaker == 'User':
                        messages.append(HumanMessage(content=content))
                    elif speaker == 'Assistant':
                        messages.append(AIMessage(content=content))

                    current_last_id = max(current_last_id, turn_id)

                except IndexError:
                    print(f"[WARNING] ログファイルの行の形式が不正です: {row}")
                except ValueError:
                     print(f"[WARNING] TurnIDが数値ではありません: {row}")

            last_turn_id = current_last_id
            last_ai_assistant = current_last_assistant
            last_model_name = current_last_model

    except Exception as e:
        print(f"[ERROR] ログファイルの読み込み中にエラーが発生しました: {e}")
        return [], 0, None, None

    print(f"ログファイル {filepath} から {len(messages)} 件のメッセージを読み込みました。最後のターンID: {last_turn_id}")
    if last_ai_assistant and last_model_name:
         print(f"ログファイルの最後の設定: Assistant={last_ai_assistant}, Model={last_model_name}")
    return messages, last_turn_id, last_ai_assistant, last_model_name

def load_assistant(ai_assistants, ai_assistant, model_name):
    module_name = ai_assistants[ai_assistant]['module']
    class_name = ai_assistants[ai_assistant]['class']
    module = importlib.import_module(module_name)
    AssistantClass = getattr(module, class_name)
    
    # ChatTogetherクラスの場合のみ、nパラメータとmax_retriesを追加
    if class_name == 'ChatTogether':
        return AssistantClass(model=model_name, n=1, max_retries=3)
    else:
        return AssistantClass(model=model_name)

def create_prompt(ai_assistant, system_message_file="system_message.txt"):
    # システムメッセージファイルが存在しない場合のエラーハンドリング
    prompt_messages = []
    # AnthropicのClaudeモデルやxAIのGrokモデルはシステムメッセージをサポート
    if ai_assistant not in ['Gemini']:
        try:
            with open(system_message_file, "r", encoding="utf-8") as file:
                system_content = file.read()
            prompt_messages.append(SystemMessagePromptTemplate.from_template(system_content))
            print(f"[INFO] システムメッセージを '{system_message_file}' から読み込みました。")
        except FileNotFoundError:
             print(f"[WARNING] システムメッセージファイル '{system_message_file}' が見つかりません。システムメッセージなしで続行します。")
        except Exception as e:
             print(f"[ERROR] システムメッセージファイル '{system_message_file}' の読み込みエラー: {e}")

    prompt_messages.extend([
        MessagesPlaceholder(variable_name="history"),
        HumanMessagePromptTemplate.from_template("{input}")
    ])
    return ChatPromptTemplate.from_messages(prompt_messages)

def save_summary_to_file(summary_content, ai_assistant, model_name):
    """まとめ内容をFoam形式でファイルに保存"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # summariesフォルダを作成（存在しない場合）
        os.makedirs(SUMMARIES_DIR, exist_ok=True)
        
        summary_filename = os.path.join(SUMMARIES_DIR, f"{timestamp}.md")
        
        with open(summary_filename, 'w', encoding='utf-8') as f:
            # シンプルなヘッダー
            f.write(f"# Chat 会話まとめ {timestamp}\n\n")
            f.write(f"- **作成日時**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
            f.write(f"- **AI Assistant**: {ai_assistant}\n")
            f.write(f"- **Model**: {model_name}\n")
            f.write(f"- **生成者**: Chat v{VERSION}\n\n")
            f.write(f"---\n\n")
            
            # AIが生成したコンテンツをそのまま挿入
            f.write(summary_content)
            f.write(f"\n\n")
            
            f.write(f"---\n")
            f.write(f"*このファイルは Chat v{VERSION} により自動生成されました*\n")
        
        print(f"\n📝 まとめを {summary_filename} に保存しました。")
        return summary_filename
    except Exception as e:
        print(f"[ERROR] まとめファイルの保存に失敗しました: {e}")
        return None

def is_summary_request(user_input):
    """まとめ要求かどうかを判定"""
    summary_keywords = [
        "まとめてください", "ここまでをまとめてください", "要約してください",
        "まとめて", "要約して", "整理してください", "整理して",
        "振り返ってください", "振り返って", "総括してください", "総括して"
    ]
    user_lower = user_input.lower().strip()
    return any(keyword in user_lower for keyword in summary_keywords)

def create_conversation_summary(conversation_history):
    """会話履歴からまとめ用テキストを作成"""
    messages = conversation_history.get_messages()
    if not messages:
        return "会話履歴がありません。"
    
    summary_text = "=== 会話履歴 ===\n\n"
    
    for i, message in enumerate(messages, 1):
        if hasattr(message, 'content'):
            if message.__class__.__name__ == 'HumanMessage':
                summary_text += f"【ユーザー {i//2 + 1}】\n{message.content}\n\n"
            elif message.__class__.__name__ == 'AIMessage':
                summary_text += f"【アシスタント {i//2 + 1}】\n{message.content}\n\n"
    
    summary_text += f"総メッセージ数: {len(messages)} 件\n"
    summary_text += f"会話ターン数: {len(messages)//2} ターン\n"
    
    return summary_text

class ChatInput:
    """チャット入力管理クラス（Chat版）"""
    def __init__(self):
        self.multi_mode = False
    
    def get_user_input(self):
        """ユーザー入力を取得（1行入力・複数行モード切り替え対応）"""
        while True:
            if not self.multi_mode:
                user_input = input("\nあなた: ").strip()
                
                # 終了コマンド
                if user_input.lower() in ["さようなら", "bye", "exit", "quit"]:
                    return user_input
                
                # 複数行モードコマンド（行の先頭で完全一致の場合のみ）
                if user_input.lower() in ["multi", "複数行"]:
                    print("=== Chat 複数行入力モード ===")
                    print("複数行でメッセージを入力してください。")
                    print("終了するには Ctrl+Z を押してください。")
                    print("1行モードに戻るには 'single' と入力してください。")
                    print("編集機能:")
                    print("  'show' - 現在の入力内容を表示")
                    print("  'clear' - 入力内容をクリア")
                    print("  'もとい' / 'ちゃいちゃい' - 直前の行を削除")
                    print("特別機能:")
                    print("  'まとめてください' - 会話履歴をAIがまとめてファイル保存")
                    print("-" * 40)
                    self.multi_mode = True
                    continue
                
                # 通常の1行入力
                if user_input:
                    return user_input
                
                # 空入力の場合は再入力を促す
                print("質問を入力してください。")
            
            else:  # 複数行モード
                lines = []
                try:
                    while True:
                        try:
                            line = input()
                            
                            # singleコマンドで1行モードに戻る
                            if line.strip().lower() == "single":
                                print("1行入力モードに戻ります。")
                                self.multi_mode = False
                                break
                            
                            # 編集コマンド群
                            elif line.strip().lower() == "show":
                                if lines:
                                    print(f"\n現在の入力内容 ({len(lines)}行):")
                                    print("-" * 20)
                                    for i, l in enumerate(lines, 1):
                                        print(f"{i:2}: {l}")
                                    print("-" * 20)
                                else:
                                    print("入力内容は空です。")
                                continue
                            
                            elif line.strip().lower() == "clear":
                                lines.clear()
                                print("入力内容をクリアしました。")
                                continue
                            
                            elif line.strip().lower() in ["もとい", "ちゃいちゃい"]:
                                if lines:
                                    removed_line = lines.pop()
                                    # 削除通知と切り取り線を表示
                                    print(f"削除: '{removed_line}'")
                                    print("-- >8 --")
                                    # 現在の内容を再表示
                                    for existing_line in lines:
                                        print(existing_line)
                                else:
                                    print("削除する行がありません。")
                                continue
                            
                            lines.append(line)
                            
                        except EOFError:
                            # Ctrl+Z が押された
                            break
                except KeyboardInterrupt:
                    print("\n入力をキャンセルしました。")
                    continue
                
                if lines:
                    result = '\n'.join(lines)
                    # 複数行入力が完了、結果を返し複数行モードは継続
                    return result
                elif self.multi_mode and not lines:
                    print("入力内容が空です。再度入力してください。")
                    # 複数行モードを継続


def get_user_input():
    """後方互換性のための関数（非推奨）"""
    global chat_input
    if 'chat_input' not in globals():
        chat_input = ChatInput()
    return chat_input.get_user_input()

def main():
    # バージョン情報を表示
    print_version_info()
    
    conversation_history = None
    conversation_log_filename = None
    ai_assistant = None
    model_name = None
    csv_writer = None
    log_file_handle = None
    id_num = 1 # デフォルトの開始ターンID
    
    # チャット入力管理クラスを初期化
    chat_input = ChatInput()

    try:
        # AI Assistants設定を読み込み
        ai_assistants = load_ai_assistants_config()
        if not ai_assistants:
            print("[ERROR] AI Assistants設定の読み込みに失敗しました。プログラムを終了します。")
            return

        # コマンドライン引数で -a や -m が指定されたかチェック
        assistant_specified = '-a' in sys.argv or '--assistant' in sys.argv
        model_specified = '-m' in sys.argv or '--model' in sys.argv

        args = parse_arguments(ai_assistants) # 引数を解析
        ai_assistant = args.assistant
        model_name = args.model
        load_log_path = args.load_log
        
        # --latest オプションの処理
        if args.latest:
            latest_log = find_latest_log()
            if latest_log:
                load_log_path = latest_log
                print(f"[INFO] --latest により最新ログ {latest_log} を読み込みます。")
            else:
                print(f"[WARNING] --latest が指定されましたが、{LOGS_DIR}/ フォルダにログファイルがありません。")
        
        # ログパスの解決
        if load_log_path:
            load_log_path = resolve_log_path(load_log_path)

        print("--- 初期設定 ---")
        print("AI Assistant:", ai_assistant)
        print("Model name:", model_name)
        print("System message file:", args.system_message)
        print("----------------")

        initial_messages = []
        last_ai_assistant_from_log = None
        last_model_name_from_log = None

        if load_log_path:
            initial_messages, last_turn_id, last_ai_assistant_from_log, last_model_name_from_log = load_history_from_csv(load_log_path)

            if last_turn_id > 0:
                id_num = last_turn_id + 1
                print(f"会話をターンID {id_num} から再開します。")

                # ログからモデル設定を継続するかの判定
                if args.ignore_log_model:
                    # --ignore-log-model が指定された場合、ログ設定を無視
                    print(f"[INFO] --ignore-log-model により、ログの設定を無視してコマンドライン設定を使用します。")
                elif args.confirm_model:
                    # --confirm-model が指定された場合、ユーザーに確認
                    print(f"\nログファイルの設定: Assistant={last_ai_assistant_from_log}, Model={last_model_name_from_log}")
                    print(f"コマンドライン設定: Assistant={ai_assistant}, Model={model_name}")
                    while True:
                        choice = input("どちらの設定を使用しますか？ [L]og設定 / [C]ommand設定 / [Q]uit: ").lower().strip()
                        if choice in ['l', 'log']:
                            if last_ai_assistant_from_log in ai_assistants:
                                ai_assistant = last_ai_assistant_from_log
                                model_name = last_model_name_from_log
                                print(f"ログ設定を採用します: {ai_assistant}/{model_name}")
                            else:
                                print(f"[WARNING] ログのAI Assistant '{last_ai_assistant_from_log}' が無効です。コマンドライン設定を使用します。")
                            break
                        elif choice in ['c', 'command']:
                            print(f"コマンドライン設定を採用します: {ai_assistant}/{model_name}")
                            break
                        elif choice in ['q', 'quit']:
                            print("プログラムを終了します。")
                            return
                        else:
                            print("L, C, Q のいずれかを入力してください。")
                elif not assistant_specified and not model_specified and last_ai_assistant_from_log and last_model_name_from_log:
                    # 従来の自動継続ロジック（デフォルト動作）
                    if last_ai_assistant_from_log in ai_assistants:
                         print(f"[INFO] -a, -m 指定なしのため、ログ設定（Assistant: {last_ai_assistant_from_log}, Model: {last_model_name_from_log}）を引き継ぎます。")
                         ai_assistant = last_ai_assistant_from_log
                         model_name = last_model_name_from_log
                    else:
                         print(f"[WARNING] ログファイルの最後のAI Assistant名 '{last_ai_assistant_from_log}' は現在有効ではありません。デフォルト設定 ({args.assistant}/{args.model}) を使用します。")
                else:
                    # -a または -m が指定されている場合、それを優先
                    print(f"[INFO] コマンドライン引数が指定されているため、指定設定（{ai_assistant}/{model_name}）を使用します。")
                
                # 最終設定を表示
                print("--- 最終設定 ---")
                print("AI Assistant:", ai_assistant)
                print("Model name:", model_name)
                print("System message file:", args.system_message)
                print("----------------")

            else:
                print("ログからの履歴読み込みに失敗したか、履歴が空でした。新規会話を開始します。")
                load_log_path = None # ログ読み込み失敗時は新規扱いにする
        else:
             print("新規会話を開始します。")

        # --- CSVログファイルの準備 ---
        log_mode = 'w' # デフォルトは新規作成モード
        write_header = True # デフォルトはヘッダー書き込みあり

        if load_log_path and initial_messages: # ログを読み込んで継続する場合
            conversation_log_filename = load_log_path # 既存のファイル名をそのまま使う
            log_mode = 'a' # 追記モードに変更
            write_header = False # ヘッダーは書き込まない
            print(f"既存のログファイル {conversation_log_filename} に追記します。")
        else: # 新規会話の場合
            timestamp_start = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # logsフォルダを作成（存在しない場合）
            os.makedirs(LOGS_DIR, exist_ok=True)
            
            conversation_log_filename = os.path.join(LOGS_DIR, f"{timestamp_start}.csv")
            print(f"会話ログを {conversation_log_filename} に保存します。")
            # log_mode と write_header はデフォルト値のまま

        try:
            # ファイルを開き、CSVライターを準備 (モードとヘッダー書き込みを動的に)
            log_file_handle = open(conversation_log_filename, log_mode, newline='', encoding='utf-8')
            csv_writer = csv.writer(log_file_handle)
            if write_header:
                header = ['Timestamp', 'TurnID', 'Speaker', 'Content', 'ExecutionTimeSeconds', 'AI_Assistant', 'ModelName', 'ExecStatus', 'IsSummary']
                csv_writer.writerow(header)

        except Exception as e:
            print(f"[ERROR] 会話ログファイル(CSV)の準備（{'追記' if log_mode == 'a' else '新規作成'}）に失敗しました: {e}")
            conversation_log_filename = None
            if log_file_handle:
                log_file_handle.close()
        # ------------------------

        if conversation_log_filename is None:
             print("[ERROR] ログファイルの準備に失敗したため、処理を続行できません。")
             return # ログファイルがないと動作できないので終了

        llm = load_assistant(ai_assistants, ai_assistant, model_name)
        prompt = create_prompt(ai_assistant, args.system_message)

        # 会話履歴を初期化
        conversation_history = ConversationHistory(max_length=MAX_HISTORY_LENGTH)
        # 読み込んだ履歴を設定
        if initial_messages:
             try:
                 # 履歴は常に最新から k*2 件に絞って復元
                 relevant_history = initial_messages[-(MAX_HISTORY_LENGTH * 2):]
                 conversation_history.extend_messages(relevant_history)
                 print(f"履歴に最後の{len(relevant_history)}件のメッセージを復元しました。")
             except Exception as e:
                  print(f"[ERROR] 履歴復元中にエラー: {e}")

        def get_history_messages():
            """履歴メッセージを取得する関数"""
            return conversation_history.get_messages()

        conversation = RunnableSequence(
            RunnablePassthrough.assign(
                history=RunnableLambda(lambda x: get_history_messages())
            ),
            prompt,
            llm
        )

        while True:
            # チャット入力クラスを使用
            user_question = chat_input.get_user_input()

            if user_question.strip().lower() in ["", "さようなら", "bye", "exit", "quit"]:
                break

            if user_question:
                # まとめ要求の検出と処理
                if is_summary_request(user_question):
                    print("📋 まとめ要求を検出しました。会話履歴をまとめています...")
                    
                    # 会話履歴からまとめ用テキストを作成
                    history_summary = create_conversation_summary(conversation_history)
                    
                    # ユーザー入力をCSVログに記録（まとめ要求として）
                    if csv_writer:
                        try:
                            timestamp_log = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            row_data = [timestamp_log, id_num, 'User', user_question, '', ai_assistant, model_name, '', 'True']
                            csv_writer.writerow(row_data)
                            log_file_handle.flush()
                        except Exception as e:
                            print(f"[ERROR] CSVログファイルへのユーザー入力書き込みに失敗しました: {e}")
                    
                    # AIによるまとめ生成
                    summary_prompt = f"""以下の会話履歴をまとめてください。主要なポイント、結論、重要な情報を整理して分かりやすくまとめてください。

{history_summary}

まとめる際は以下の点を心がけてください：
- 重要なキーワードや概念は [[キーワード]] の形式で囲んでリンク化してください
- 関連するトピックや技術用語も [[]] で囲んでください
- #タグ も適切に付与してください
- 他のノートとのつながりを意識した書き方をしてください

上記の会話を簡潔にまとめてください："""
                    
                    start_time = time.time()
                    ai_response_content = None
                    exec_status = 'Failure'
                    response_message = None
                    
                    # AIによるまとめ生成（リトライ機能付き）
                    max_retries = 3
                    retry_delay = 60
                    
                    for attempt in range(max_retries):
                        try:
                            response_message = conversation.invoke({"input": summary_prompt})
                            if isinstance(response_message, AIMessage):
                                ai_response_content = response_message.content
                                exec_status = 'Success'
                                break
                            else:
                                ai_response_content = 'まとめの生成に失敗しました。'
                                break
                        except Exception as e:
                            error_str = str(e)
                            print(f"まとめ生成エラー (試行 {attempt + 1}/{max_retries}): {e}")
                            
                            # APIエラーコードを検出
                            error_code = detect_api_error(error_str)
                            
                            if error_code:
                                should_retry = handle_api_error(error_code, error_str, attempt, max_retries, retry_delay, conversation_history)
                                if should_retry:
                                    continue
                                else:
                                    formatted_error = format_error_message(error_code, error_str)
                                    ai_response_content = f"まとめ生成エラー: {formatted_error}"
                                    break
                            else:
                                # 従来のrate limit検出（フォールバック）
                                if "429" in error_str or "rate limit" in error_str.lower():
                                    if attempt < max_retries - 1:
                                        wait_time = retry_delay * (2 ** attempt)
                                        print(f"レート制限に達しました。{wait_time}秒待機してから再試行します...")
                                        time.sleep(wait_time)
                                        continue
                                
                                ai_response_content = f"まとめ生成エラー: {e}"
                                if attempt == max_retries - 1:
                                    print(f"最大リトライ回数に達しました。エラー: {e}")
                                break
                    
                    end_time = time.time()
                    run_time = round(end_time - start_time, 3)
                    
                    if ai_response_content:
                        print(f"\n📋 会話まとめ（{ai_assistant}:{model_name}）:\n{ai_response_content}")
                        
                        # まとめをファイルに保存
                        summary_filename = save_summary_to_file(ai_response_content, ai_assistant, model_name)
                        
                        # ⚠️ まとめは会話履歴に追加しない（トークン節約のため）
                        # conversation_history.add_message(HumanMessage(content=user_question))
                        # if response_message:
                        #     conversation_history.add_message(response_message)
                        print("💡 まとめはトークン節約のため会話履歴に含めません。")
                    
                    print(f"\n--------------------\n実行時間: {run_time:.3f}秒\n--------------------")
                    
                    # アシスタント応答をCSVログに記録（まとめとして）
                    if csv_writer:
                        try:
                            timestamp_log = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            row_data = [timestamp_log, id_num, 'Assistant', ai_response_content, run_time, ai_assistant, model_name, exec_status, 'True']
                            csv_writer.writerow(row_data)
                            log_file_handle.flush()
                        except Exception as e:
                            print(f"[ERROR] CSVログファイルへのアシスタント応答書き込みに失敗しました: {e}")
                    
                    id_num += 1
                    continue  # まとめ処理完了、通常の処理をスキップ
                
                # --- 通常のユーザー入力をCSVログに記録 ---
                if csv_writer:
                    try:
                        timestamp_log = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        row_data = [timestamp_log, id_num, 'User', user_question, '', ai_assistant, model_name, '', 'False']
                        csv_writer.writerow(row_data)
                        log_file_handle.flush() # バッファをフラッシュして即時書き込み
                    except Exception as e:
                        print(f"[ERROR] CSVログファイルへのユーザー入力書き込みに失敗しました: {e}")
                # ----------------------------------

                start_time = time.time()
                ai_response_content = None
                exec_status = 'Failure'
                response_message = None
                
                # リトライ機能付きでAPI呼び出し
                max_retries = 3
                retry_delay = 60  # 初期待機時間（秒）
                
                for attempt in range(max_retries):
                    try:
                        response_message = conversation.invoke({"input": user_question})
                        if isinstance(response_message, AIMessage):
                            ai_response_content = response_message.content
                            # 会話履歴に追加
                            conversation_history.add_message(HumanMessage(content=user_question))
                            conversation_history.add_message(response_message)
                            exec_status = 'Success'
                            break  # 成功したらループを抜ける
                        else:
                            ai_response_content = 'No valid output found from AI.'
                            break
                    except Exception as e:
                        error_str = str(e)
                        print(f"エラーが発生しました (試行 {attempt + 1}/{max_retries}): {e}")
                        
                        # APIエラーコードを検出
                        error_code = detect_api_error(error_str)
                        
                        if error_code:
                            should_retry = handle_api_error(error_code, error_str, attempt, max_retries, retry_delay, conversation_history)
                            if should_retry:
                                continue
                            else:
                                formatted_error = format_error_message(error_code, error_str)
                                ai_response_content = f"Error: {formatted_error}"
                                break
                        else:
                            # 従来のrate limit検出（フォールバック）
                            if "429" in error_str or "rate limit" in error_str.lower():
                                if attempt < max_retries - 1:  # 最後の試行でない場合
                                    wait_time = retry_delay * (2 ** attempt)  # 指数バックオフ
                                    print(f"レート制限に達しました。{wait_time}秒待機してから再試行します...")
                                    time.sleep(wait_time)
                                    continue
                            
                            # その他のエラーまたは最後の試行の場合
                            ai_response_content = f"Error: {e}"
                            if attempt == max_retries - 1:
                                print(f"最大リトライ回数に達しました。エラー: {e}")
                            break

                end_time = time.time()
                run_time = round(end_time - start_time, 3)

                if ai_response_content:
                    print(f"\nアシスタント（{ai_assistant}:{model_name}）:\n{ai_response_content}")

                print(f"\n--------------------\n実行時間: {run_time:.3f}秒\n--------------------")

                # --- アシスタント応答をCSVログに記録 ---
                if csv_writer:
                    try:
                        timestamp_log = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        row_data = [timestamp_log, id_num, 'Assistant', ai_response_content, run_time, ai_assistant, model_name, exec_status, 'False']
                        csv_writer.writerow(row_data)
                        log_file_handle.flush() # バッファをフラッシュして即時書き込み
                    except Exception as e:
                        print(f"[ERROR] CSVログファイルへのアシスタント応答書き込みに失敗しました: {e}")
                # ------------------------------------

                id_num += 1

    except Exception as e:
         # main 関数レベルでの予期せぬエラー
         print(f"[FATAL ERROR] プログラムの実行中に予期せぬエラーが発生しました: {e}")
         import traceback
         traceback.print_exc() # トレースバックを出力

    finally:
        print("Chat を終了します。")
        if log_file_handle:
            try:
                log_file_handle.close()
                if conversation_log_filename: # ファイル名が確定していれば表示
                     print(f"会話ログを {conversation_log_filename} に保存しました。")
            except Exception as e:
                print(f"[ERROR] 会話ログファイル(CSV)のクローズに失敗しました: {e}")

if __name__ == "__main__":
    main()
