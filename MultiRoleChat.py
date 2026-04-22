# MultiRoleChat - 複数ロール間でのチャットボット
# Version: 1.0.0
# Features: 
# - 複数のAIアシスタント間での会話
# - ロール指定による専門的な対話
# - 会話履歴の保存と読み込み
# - 動的なロール追加・削除

import sys
import os
import csv
import time
import json
import importlib
from datetime import datetime

# Optional code saving functionality
try:
    from code_saver import CodeSaver
    CODE_SAVING_ENABLED = True
except ImportError:
    CODE_SAVING_ENABLED = False
    print("[INFO] code_saver.py not found. Code saving disabled.")
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
import argparse
from typing import Annotated, TypedDict
import asyncio
import concurrent.futures
from langgraph.graph import StateGraph, END

# Version information
VERSION = "1.2.0"
VERSION_DATE = "2026-04-22"

# Configuration files
AI_ASSISTANTS_CONFIG_FILE = "ai_assistants_config.csv"
MODEL_COSTS_CONFIG_FILE = "model_costs.csv"

# Logs directories
MULTI_LOGS_DIR = "multi_logs"
MULTI_SUMMARIES_DIR = "multi_summaries"

MAX_HISTORY_LENGTH = 10

# ワークフロー用履歴設定
WORKFLOW_HISTORY_LENGTH = 10  # 通常のワークフローでの前ステップ保持数
ITERATIVE_WORKFLOW_HISTORY_LENGTH = 10  # 反復ワークフローでの前回反復結果保持数
CURRENT_ITERATION_HISTORY_LENGTH = 5   # 反復ワークフローでの現在反復内ステップ保持数

# ワークフロー用応答長制限
WORKFLOW_RESPONSE_LIMIT = 500  # ワークフロー実行時の推奨文字数上限

def load_model_costs():
    """CSVファイルからモデルコスト情報を読み込む"""
    model_costs = {}
    
    if not os.path.exists(MODEL_COSTS_CONFIG_FILE):
        print(f"[WARNING] モデルコスト設定ファイル '{MODEL_COSTS_CONFIG_FILE}' が見つかりません。デフォルト値を使用します。")
        return {
            'default': {'input': 0.001/1000, 'output': 0.003/1000}
        }
    
    try:
        with open(MODEL_COSTS_CONFIG_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                model_name = row['model']
                # 1000トークンあたりの価格を1トークンあたりに変換
                input_cost = float(row['input_cost_per_1k_tokens']) / 1000
                output_cost = float(row['output_cost_per_1k_tokens']) / 1000
                
                model_costs[model_name] = {
                    'input': input_cost,
                    'output': output_cost,
                    'provider': row['provider'],
                    'date_updated': row['date_updated'],
                    'currency': row['currency'],
                    'notes': row.get('notes', '')
                }
        
        print(f"[INFO] モデルコスト設定を {MODEL_COSTS_CONFIG_FILE} から読み込みました。")
        return model_costs
    except Exception as e:
        print(f"[ERROR] モデルコスト設定ファイルの読み込みに失敗しました: {e}")
        return {
            'default': {'input': 0.001/1000, 'output': 0.003/1000}
        }

# 動的にモデルコストを読み込む
MODEL_COSTS = load_model_costs()

class TokenUsageTracker:
    """トークン使用量とコスト追跡クラス"""
    def __init__(self):
        self.session_usage = {
            'total_input_tokens': 0,
            'total_output_tokens': 0,
            'total_cost': 0.0,
            'model_breakdown': {},
            'response_times': {},  # 応答時間の記録
            'request_count': 0     # リクエスト総数
        }
    
    def estimate_tokens(self, text):
        """テキストのトークン数を推定（簡易版）"""
        # 簡易推定: 英語は4文字/トークン、日本語は2文字/トークン
        if not text:
            return 0
        
        # 日本語文字数をカウント
        japanese_chars = len([c for c in text if ord(c) > 127])
        english_chars = len(text) - japanese_chars
        
        # 推定トークン数
        estimated_tokens = (japanese_chars / 2) + (english_chars / 4)
        return max(1, int(estimated_tokens))
    
    def add_usage(self, model_name, input_text, output_text, response_time=None):
        """使用量とレスポンス時間を記録"""
        input_tokens = self.estimate_tokens(input_text)
        output_tokens = self.estimate_tokens(output_text)
        
        # コスト計算
        model_cost = MODEL_COSTS.get(model_name, MODEL_COSTS['default'])
        input_cost = input_tokens * model_cost['input']
        output_cost = output_tokens * model_cost['output']
        total_cost = input_cost + output_cost
        
        # セッション全体に加算
        self.session_usage['total_input_tokens'] += input_tokens
        self.session_usage['total_output_tokens'] += output_tokens
        self.session_usage['total_cost'] += total_cost
        self.session_usage['request_count'] += 1
        
        # モデル別内訳
        if model_name not in self.session_usage['model_breakdown']:
            self.session_usage['model_breakdown'][model_name] = {
                'input_tokens': 0, 
                'output_tokens': 0, 
                'cost': 0.0,
                'requests': 0,
                'total_response_time': 0.0,
                'avg_response_time': 0.0
            }
        
        self.session_usage['model_breakdown'][model_name]['input_tokens'] += input_tokens
        self.session_usage['model_breakdown'][model_name]['output_tokens'] += output_tokens
        self.session_usage['model_breakdown'][model_name]['cost'] += total_cost
        self.session_usage['model_breakdown'][model_name]['requests'] += 1
        
        # 応答時間の記録
        if response_time is not None:
            self.session_usage['model_breakdown'][model_name]['total_response_time'] += response_time
            self.session_usage['model_breakdown'][model_name]['avg_response_time'] = (
                self.session_usage['model_breakdown'][model_name]['total_response_time'] / 
                self.session_usage['model_breakdown'][model_name]['requests']
            )
        
        return {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cost': total_cost,
            'model': model_name,
            'response_time': response_time
        }
    
    def get_session_summary(self):
        """セッション全体のサマリーを取得"""
        return self.session_usage.copy()
    
    def format_cost_info(self, usage_info):
        """コスト情報をフォーマット"""
        if not usage_info:
            return "不明 (レガシーログ)"
        
        return f"${usage_info['cost']:.4f} (入力: {usage_info['input_tokens']}tokens, 出力: {usage_info['output_tokens']}tokens)"
    
    def get_model_cost_info(self, model_name):
        """指定されたモデルのコスト情報を取得"""
        cost_info = MODEL_COSTS.get(model_name, MODEL_COSTS.get('default', {}))
        if cost_info:
            provider = cost_info.get('provider', '不明')
            date_updated = cost_info.get('date_updated', '不明')
            currency = cost_info.get('currency', 'USD')
            input_cost_per_1k = cost_info['input'] * 1000
            output_cost_per_1k = cost_info['output'] * 1000
            
            return {
                'provider': provider,
                'date_updated': date_updated,
                'currency': currency,
                'input_cost_per_1k': input_cost_per_1k,
                'output_cost_per_1k': output_cost_per_1k
            }
        return None
    
    def get_performance_stats(self):
        """プロバイダとモデル別のパフォーマンス統計を取得"""
        stats = {
            'total_requests': self.session_usage['request_count'],
            'models': {}
        }
        
        for model_name, data in self.session_usage['model_breakdown'].items():
            stats['models'][model_name] = {
                'requests': data['requests'],
                'avg_response_time': data['avg_response_time'],
                'total_tokens': data['input_tokens'] + data['output_tokens'],
                'total_cost': data['cost'],
                'tokens_per_second': (data['input_tokens'] + data['output_tokens']) / data['total_response_time'] if data['total_response_time'] > 0 else 0
            }
        
        return stats
    
    def print_performance_report(self):
        """パフォーマンスレポートを出力"""
        stats = self.get_performance_stats()
        
        print("\n📊 パフォーマンス統計")
        print("=" * 60)
        print(f"総リクエスト数: {stats['total_requests']}")
        
        if not stats['models']:
            print("統計データがありません")
            return
        
        print("\n🏁 モデル別パフォーマンス:")
        print("-" * 60)
        
        # ソート（平均応答時間順）
        sorted_models = sorted(
            stats['models'].items(), 
            key=lambda x: x[1]['avg_response_time'] if x[1]['avg_response_time'] > 0 else float('inf')
        )
        
        for model_name, data in sorted_models:
            print(f"🤖 {model_name}")
            print(f"   📊 リクエスト数: {data['requests']}")
            if data['avg_response_time'] > 0:
                print(f"   ⏱️ 平均応答時間: {data['avg_response_time']:.2f}秒")
                print(f"   🚀 処理速度: {data['tokens_per_second']:.1f} tokens/秒")
            print(f"   💰 総コスト: ${data['total_cost']:.4f}")
            print(f"   📝 総トークン: {data['total_tokens']}")
            print()
        
        print("=" * 60)

def print_version_info():
    """バージョン情報を表示"""
    print(f"🎭 MultiRoleChat - マルチロールAIチャットボット v{VERSION} ({VERSION_DATE})")
    print("=" * 70)
    print("✨ 機能:")
    print("  🎭 複数ロール - 異なる専門性を持つAIアシスタント間での会話")
    print("  💬 ロール間対話 - アシスタント同士の自動会話機能")
    print("  📋 会話管理 - 全ロールの発言履歴を統合管理")
    print("  🔄 動的ロール管理 - 実行中のロール追加・削除")
    print("=" * 70)

class MultiRoleConversationHistory:
    """マルチロール会話履歴を管理するクラス"""
    def __init__(self, max_length=MAX_HISTORY_LENGTH * 2):  # マルチロールでは2倍の履歴を保持
        self.max_length = max_length
        self.messages = []
    
    def add_message(self, message, role=None):
        """メッセージを追加（ロール情報付き）"""
        if role:
            # ロール情報をメタデータとして追加
            if hasattr(message, 'additional_kwargs'):
                message.additional_kwargs['role'] = role
            else:
                message.additional_kwargs = {'role': role}
        
        self.messages.append(message)
        
        # 最大長を超えた場合、古いメッセージを削除
        if len(self.messages) > self.max_length:
            self.messages = self.messages[-self.max_length:]
    
    def get_messages(self):
        """メッセージリストを取得"""
        return self.messages
    
    def get_messages_for_role(self, target_role):
        """特定のロール向けにフィルタリングしたメッセージを取得"""
        # 他のロールの内部思考は除外し、ユーザーと自分のメッセージのみを含める
        filtered_messages = []
        for msg in self.messages:
            role = getattr(msg, 'additional_kwargs', {}).get('role', 'user')
            if role == 'user' or role == target_role:
                filtered_messages.append(msg)
        return filtered_messages

class MultiRoleManager:
    """マルチロール管理クラス"""
    def __init__(self, ai_assistants, use_fast=False, config_file=None, organization_name=None):
        self.ai_assistants = ai_assistants
        self.use_fast = use_fast
        self.config_file = config_file  # 古いシステム用（非推奨）
        self.organization_name = organization_name  # コマンドライン引数からの組織名
        self.organization_config = None  # 組織設定データ
        self.active_roles = {}
        self.role_prompts = {}
        self.role_types = {}  # 各ロールのタイプを保存（moderator/member）
        self.conversation_history = MultiRoleConversationHistory()
        # 組織・設定ファイル情報を保持
        self.organization_info = self._detect_organization_info()
        # トークン使用量追跡
        self.token_tracker = TokenUsageTracker()
        # 現在のワークフロー情報を保持
        self.current_workflow_info = None
        # ワークフロー実行中の全レスポンスを蓄積（最終保存用）
        self.workflow_responses = []
    
    def _detect_organization_info(self):
        """設定ファイルから組織情報を検出"""
        org_info = {
            'config_file_path': os.path.abspath(self.config_file) if self.config_file else None,
            'organization': 'unknown',
            'organization_path': None
        }
        
        # コマンドライン引数の組織名を最優先で使用
        if self.organization_name:
            org_info['organization'] = self.organization_name
            org_info['organization_path'] = f'organizations/{self.organization_name}/'
            return org_info
        
        # config_fileがない場合は早期リターン
        if not self.config_file:
            return org_info
        
        # 設定ファイル名から組織を推測
        config_basename = os.path.basename(self.config_file)
        if 'tech_startup' in config_basename:
            org_info['organization'] = 'tech_startup'
            org_info['organization_path'] = 'organizations/tech_startup/'
        elif 'consulting_firm' in config_basename:
            org_info['organization'] = 'consulting_firm'
            org_info['organization_path'] = 'organizations/consulting_firm/'
        elif 'default_company' in config_basename:
            org_info['organization'] = 'default_company'
            org_info['organization_path'] = 'organizations/default_company/'
        
        return org_info
    
    def add_role(self, role_name, assistant_name, model_name, system_prompt, source_file=None, role_type="member"):
        """新しいロールを追加"""
        """新しいロールを追加"""
        if assistant_name not in self.ai_assistants:
            raise ValueError(f"Unknown assistant: {assistant_name}")
        
        # ロールタイプを保存
        self.role_types[role_name] = role_type
        
        # アシスタントのインスタンスを作成
        assistant_instance = self.load_assistant(assistant_name, model_name, self.use_fast)
        
        # プロンプトテンプレートを作成
        prompt_template = self.create_role_prompt(system_prompt)
        
        # 会話チェーンを作成
        conversation_chain = RunnableSequence(
            RunnablePassthrough.assign(
                history=RunnableLambda(lambda x: self.conversation_history.get_messages_for_role(role_name))
            ),
            prompt_template,
            assistant_instance
        )
        
        self.active_roles[role_name] = {
            'assistant': assistant_name,
            'model': model_name,
            'system_prompt': system_prompt,
            'conversation': conversation_chain,
            'instance': assistant_instance,
            'source_file': source_file,
            'organization': self.organization_info['organization'],
            'config_path': self.organization_info['config_file_path']
        }
        
        print(f"✅ ロール '{role_name}' を追加しました（{assistant_name}:{model_name}）")
        print(f"   システムプロンプト: {system_prompt[:100]}...")
    
    def remove_role(self, role_name):
        """ロールを削除"""
        if role_name in self.active_roles:
            del self.active_roles[role_name]
            print(f"❌ ロール '{role_name}' を削除しました")
        else:
            print(f"⚠️ ロール '{role_name}' は存在しません")
    
    def list_roles(self):
        """現在のロール一覧を表示"""
        if not self.active_roles:
            print("現在アクティブなロールはありません")
            return
        
        print("\n📋 現在のアクティブロール:")
        for role_name, role_info in self.active_roles.items():
            assistant = role_info.get('assistant', 'Unknown')
            model = role_info.get('model', 'Unknown')
            system_prompt = role_info.get('system_prompt', '')
            organization = role_info.get('organization', 'Unknown')
            config_path = role_info.get('config_path', 'Unknown')
            source_file = role_info.get('source_file', 'Unknown')
            print(f"  🎭 {role_name}:")
            print(f"      Assistant: {assistant}")
            print(f"      Model: {model}")
            print(f"      Organization: {organization}")
            print(f"      Config Path: {config_path}")
            print(f"      Source File: {source_file}")
            print(f"      システムプロンプト: {system_prompt[:100]}...")
            print()
    
    def load_assistant(self, assistant_name, model_name, use_fast=False):
        """アシスタントインスタンスを作成"""
        module_name = self.ai_assistants[assistant_name]['module']
        class_name = self.ai_assistants[assistant_name]['class']
        
        # fast_modelが指定されている場合は使用
        if use_fast and self.ai_assistants[assistant_name].get('fast_model'):
            model_name = self.ai_assistants[assistant_name]['fast_model']
            print(f"🚀 Fast Model使用: {assistant_name} -> {model_name}")
        
        module = importlib.import_module(module_name)
        AssistantClass = getattr(module, class_name)
        
        # ChatTogetherクラスの場合のみ、nパラメータとmax_retriesを追加
        if class_name == 'ChatTogether':
            return AssistantClass(model=model_name, n=1, max_retries=3)
        else:
            return AssistantClass(model=model_name)
    
    def create_role_prompt(self, system_prompt):
        """ロール用のプロンプトテンプレートを作成"""
        prompt_messages = [
            SystemMessagePromptTemplate.from_template(system_prompt),
            MessagesPlaceholder(variable_name="history"),
            HumanMessagePromptTemplate.from_template("{input}")
        ]
        return ChatPromptTemplate.from_messages(prompt_messages)
    
    def get_response_from_role(self, role_name, user_input):
        """指定されたロールから応答を取得"""
        if role_name not in self.active_roles:
            return f"エラー: ロール '{role_name}' は存在しません"
        
        try:
            role_info = self.active_roles[role_name]
            
            # 応答時間の測定開始
            start_time = time.time()
            response = role_info['conversation'].invoke({"input": user_input})
            end_time = time.time()
            
            response_time = end_time - start_time
            
            if isinstance(response, AIMessage):
                # 応答を履歴に追加（ロール情報付き）
                self.conversation_history.add_message(HumanMessage(content=user_input), 'user')
                self.conversation_history.add_message(response, role_name)
                
                # contentが文字列であることを確認
                content = response.content
                if isinstance(content, list):
                    # リストの場合は文字列に変換
                    content = ' '.join(str(item) for item in content)
                
                response_text = str(content) if content else "応答が空でした"
                
                # 個別のコード保存は無効化（ワークフロー完了時に統一保存）
                # if CODE_SAVING_ENABLED:
                #     try:
                #         code_saver = CodeSaver()
                #         session_info = code_saver.save_ai_response_complete(
                #             response_text, role_name, "role_response"
                #         )
                #         if session_info and session_info.get('saved_files'):
                #             print(f"\n💾 {len(session_info['saved_files'])} ファイル保存: sandbox/session_{session_info['session_id']}/")
                #     except Exception as save_error:
                #         # エラーがあってもメインフローは継続
                #         pass
                
                # トークン使用量と応答時間を記録
                model_name = role_info.get('model', 'unknown')
                usage_info = self.token_tracker.add_usage(model_name, user_input, response_text, response_time)
                
                # ワークフロー実行中の場合、レスポンスを蓄積
                if hasattr(self, 'workflow_responses'):
                    self.workflow_responses.append({
                        'role': role_name,
                        'response': response_text,
                        'timestamp': datetime.now().isoformat()
                    })
                
                return response_text
            else:
                return "応答の取得に失敗しました"
                
        except Exception as e:
            error_msg = str(e)
            if "rate_limit_exceeded" in error_msg:
                return f"⚠️ API制限に達しました。しばらく待ってから再試行してください。"
            elif "credit balance is too low" in error_msg:
                return f"⚠️ APIクレジットが不足しています。"
            elif "429" in error_msg:
                return f"⚠️ レート制限エラー: トークン数を削減する必要があります。"
            else:
                return f"エラー: {e}"
    
    def role_to_role_conversation(self, sender_role, receiver_role, message, max_turns=3):
        """ロール間での自動会話を実行"""
        if sender_role not in self.active_roles or receiver_role not in self.active_roles:
            print("指定されたロールが存在しません")
            return
        
        print(f"\n🔄 {sender_role} ⟷ {receiver_role} の会話を開始します (最大{max_turns}ターン)")
        print("=" * 50)
        
        conversation_log = []
        current_message = message
        current_sender = sender_role
        current_receiver = receiver_role
        
        # 初期メッセージをログに記録
        conversation_log.append(f"[{current_sender}] {current_message}")
        
        for turn in range(max_turns):
            print(f"\n💬 {current_sender} → {current_receiver}:")
            print(f"「{current_message}」")
            
            # 受信側ロールからの応答を取得
            response = self.get_response_from_role(current_receiver, current_message)
            if isinstance(response, str):
                formatted_response = response.replace('\\n', '\n')
            else:
                formatted_response = str(response) if response else ""
            print(f"\n🎭 {current_receiver} の応答:")
            print(f"「{formatted_response}」")
            
            # 応答をログに記録
            conversation_log.append(f"[{current_receiver}] {response}")
            
            # 送信者と受信者を交代
            current_sender, current_receiver = current_receiver, current_sender
            current_message = response
            
            # 簡単な終了条件チェック
            if any(end_word in response.lower() for end_word in ['ありがとう', 'わかりました', '以上です', '終了']):
                print(f"\n✅ 会話が自然に終了しました（ターン {turn + 1}）")
                break
        
        print("=" * 50)
        
        # 会話ログを保存
        topic = f"{sender_role}と{receiver_role}の対話"
        self.save_meeting_log(topic, [sender_role, receiver_role], conversation_log, "", "conversation")
        
        return conversation_log

    def execute_iterative_workflow(self, workflow_name, topic, max_iterations=5):
        """反復実行可能なワークフローを実行（LangGraph対応: 条件分岐ループ）"""
        if hasattr(self, 'organization_config') and self.organization_config:
            config = self.organization_config
        else:
            config = load_multi_role_config(self.config_file)

        if not config or 'workflows' not in config or workflow_name not in config['workflows']:
            print(f"ワークフロー '{workflow_name}' が見つかりません")
            return

        workflow = config['workflows'][workflow_name]
        max_iter = workflow.get('max_iterations', max_iterations)

        self.current_workflow_info = {
            'name': workflow_name,
            'display_name': workflow.get('name', workflow_name),
            'description': workflow.get('description', '説明なし'),
            'execution_mode': 'iterative',
            'iteration_count': 0,
            'max_iterations': max_iter,
            'test_results': None
        }
        self.workflow_responses = []

        print(f"\n🔄 反復ワークフロー '{workflow['name']}' を開始します")
        print(f"📝 説明: {workflow.get('description', '')}")
        print(f"💬 トピック: {topic}")
        print(f"🔄 最大反復回数: {max_iter}")
        print("=" * 60)

        # --- LangGraph State 定義 ---
        class IterativeState(TypedDict):
            topic: str
            all_results: list
            current_results: list
            iteration: int
            test_passed: bool

        steps = workflow.get('steps', [])
        role_manager_ref = self

        def run_iteration(state: IterativeState) -> IterativeState:
            """1回の反復（全ステップ）を実行するノード"""
            iteration = state['iteration']
            print(f"\n🔄 反復 {iteration}/{max_iter}")
            print("-" * 40)

            current_results = []
            test_passed = False

            for i, step in enumerate(steps, 1):
                role_name = step['role']
                action = step['action']

                if role_name not in role_manager_ref.active_roles:
                    print(f"⚠️ ロール '{role_name}' が見つかりません。スキップします。")
                    continue

                print(f"\n📋 ステップ {i}: {role_name}")
                print(f"🎯 アクション: {action}")
                print("-" * 40)

                input_text = f"{topic}\n\n{action}"
                if state['all_results']:
                    input_text += f"\n\n前回の反復結果:\n" + "\n".join([str(r) for r in state['all_results'][-ITERATIVE_WORKFLOW_HISTORY_LENGTH:]])
                if current_results:
                    input_text += f"\n\n現在の反復での前ステップ結果:\n" + "\n".join(current_results[-CURRENT_ITERATION_HISTORY_LENGTH:])
                input_text += f"\n\n【重要】反復ワークフロー実行中です。以下の点を守ってください：\n- 応答は{WORKFLOW_RESPONSE_LIMIT}文字以内で簡潔に\n- 箇条書きを活用\n- 前回からの改善点を重視\n- 次の反復に繋がるよう明確に"

                response = role_manager_ref.get_response_from_role(role_name, input_text)
                formatted = response.replace('\\n', '\n') if isinstance(response, str) else str(response or "")
                print(f"💬 {role_name}: {formatted}")
                current_results.append(f"[{role_name}] {response}")

                if role_name == "コードテスター" and "✅ テスト結果: 合格" in str(response):
                    test_passed = True
                    print("🎉 テスト合格！")
                elif role_name == "コードテスター" and "❌ テスト結果: 不合格" in str(response):
                    print("⚠️ テスト不合格。修正が必要です。")

            return {
                "topic": state['topic'],
                "all_results": state['all_results'] + current_results,
                "current_results": current_results,
                "iteration": iteration + 1,
                "test_passed": test_passed
            }

        def should_continue(state: IterativeState) -> str:
            """継続するか終了するかを判定するエッジ関数"""
            if state['test_passed']:
                return "end"
            if state['iteration'] > max_iter:
                return "end"
            return "continue"

        # --- グラフ構築 ---
        graph = StateGraph(IterativeState)
        graph.add_node("iterate", run_iteration)
        graph.set_entry_point("iterate")
        graph.add_conditional_edges(
            "iterate",
            should_continue,
            {"continue": "iterate", "end": END}
        )

        app = graph.compile()
        final_state = app.invoke({
            "topic": topic,
            "all_results": [],
            "current_results": [],
            "iteration": 1,
            "test_passed": False
        })

        all_results = final_state['all_results']
        iteration = final_state['iteration'] - 1
        test_passed = final_state['test_passed']

        print("=" * 60)
        if test_passed:
            print(f"✅ ワークフロー完了（テスト合格: 反復{iteration}回）")
        else:
            print(f"⚠️ ワークフロー終了（最大反復回数{max_iter}回に到達）")

        if self.current_workflow_info:
            self.current_workflow_info['iteration_count'] = iteration
            self.current_workflow_info['test_results'] = test_passed

        workflow_participants = [step['role'] for step in steps]
        workflow_info = self.current_workflow_info or {
            'name': workflow_name,
            'display_name': workflow.get('name', workflow_name),
            'description': workflow.get('description', ''),
            'execution_mode': 'iterative',
            'iteration_count': iteration,
            'max_iterations': max_iter,
            'test_results': test_passed
        }

        self.save_meeting_log(topic, workflow_participants, all_results, f"反復{iteration}回", "workflow", workflow_info=workflow_info)
        self._save_workflow_final_code(topic, workflow_name)

        return all_results

    def execute_workflow(self, workflow_name, topic):
        """ワークフローを実行（LangGraph対応: 直列・並列・反復）"""
        if hasattr(self, 'organization_config') and self.organization_config:
            config = self.organization_config
        else:
            config = load_multi_role_config(self.config_file)

        if not config or 'workflows' not in config or workflow_name not in config['workflows']:
            print(f"ワークフロー '{workflow_name}' が見つかりません")
            if config and 'workflows' in config:
                available_workflows = list(config['workflows'].keys())
                if available_workflows:
                    print("利用可能なワークフロー:")
                    for wf in available_workflows:
                        print(f"  - {wf}")
            return

        workflow = config['workflows'][workflow_name]

        self.current_workflow_info = {
            'name': workflow_name,
            'display_name': workflow.get('name', workflow_name),
            'description': workflow.get('description', '説明なし'),
            'execution_mode': 'single',
            'iteration_count': 1,
            'max_iterations': 1,
            'test_results': None
        }
        self.workflow_responses = []

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"multi_logs/{timestamp}_{workflow_name}.md"
        os.makedirs("multi_logs", exist_ok=True)
        self._initialize_workflow_log(log_filename, workflow, topic, workflow_name)
        _workflow_start = time.time()

        print(f"\n🔄 ワークフロー '{workflow['name']}' を開始します")
        print(f"📝 ログファイル: {log_filename}")
        print(f"トピック: {topic}")
        print("=" * 60)

        # --- LangGraph State 定義 ---
        class WorkflowState(TypedDict):
            topic: str
            results: list
            step_index: int

        steps = workflow.get('steps', [])
        parallel_groups = workflow.get('parallel_steps', [])
        response_limit = workflow.get('response_limit', WORKFLOW_RESPONSE_LIMIT)
        style = workflow.get('style', '簡潔')
        format_pref = workflow.get('format', '箇条書き推奨')

        role_manager_ref = self  # クロージャ用

        def make_step_node(step_index, role_name, action):
            """直列ステップ用ノードを生成"""
            def node(state: WorkflowState) -> WorkflowState:
                print(f"\n📋 Step {step_index + 1}: {role_name} - {action}")
                print("-" * 40)
                input_text = f"{state['topic']}\n\n{action}"
                if state['results']:
                    input_text += f"\n\n前のステップの結果:\n" + "\n".join(state['results'][-WORKFLOW_HISTORY_LENGTH:])
                input_text += f"\n\n【重要】ワークフロー実行中です。以下の点を守ってください：\n- 応答は{response_limit}文字以内で{style}に\n- {format_pref}\n- 重要なポイントのみに絞る"
                _t0 = time.time()
                response = role_manager_ref.get_response_from_role(role_name, input_text)
                _elapsed = time.time() - _t0
                formatted = response.replace('\\n', '\n') if isinstance(response, str) else str(response or "")
                print(f"🎭 {role_name}（{_elapsed:.2f}秒）: {formatted}")
                role_manager_ref._append_step_to_log(log_filename, step_index + 1, role_name, action, formatted, elapsed=_elapsed)
                print(f"📝 ステップ {step_index + 1} をログに保存しました")
                new_results = state['results'] + [f"[{role_name}] {response}"]
                return {"topic": state['topic'], "results": new_results, "step_index": step_index + 1}
            return node

        def make_parallel_node(group_index, group):
            """並列グループ用ノードを生成"""
            def node(state: WorkflowState) -> WorkflowState:
                print(f"\n⚡ 並列グループ {group_index + 1} 開始（{len(group)}ロール同時実行）")
                print("-" * 40)
                input_text_base = state['topic']
                if state['results']:
                    input_text_base += "\n\n前のステップの結果:\n" + "\n".join(state['results'][-WORKFLOW_HISTORY_LENGTH:])
                input_text_base += f"\n\n【重要】ワークフロー実行中です。以下の点を守ってください：\n- 応答は{response_limit}文字以内で{style}に\n- {format_pref}"

                def call_role(step):
                    role_name = step['role']
                    action = step.get('action', '')
                    inp = input_text_base + (f"\n\n{action}" if action else "")
                    _t0 = time.time()
                    response = role_manager_ref.get_response_from_role(role_name, inp)
                    return role_name, response, time.time() - _t0

                new_results = list(state['results'])
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = {executor.submit(call_role, step): step for step in group}
                    for future in concurrent.futures.as_completed(futures):
                        role_name, response, _elapsed = future.result()
                        formatted = response.replace('\\n', '\n') if isinstance(response, str) else str(response or "")
                        print(f"🎭 {role_name}（{_elapsed:.2f}秒）: {formatted}")
                        step_num = len(new_results) + 1
                        action = futures[future].get('action', '')
                        role_manager_ref._append_step_to_log(log_filename, step_num, role_name, action, formatted, elapsed=_elapsed)
                        new_results.append(f"[{role_name}] {response}")

                return {"topic": state['topic'], "results": new_results, "step_index": state['step_index']}
            return node

        # --- グラフ構築 ---
        graph = StateGraph(WorkflowState)

        node_names = []

        # 直列ステップをノードとして追加
        for i, step in enumerate(steps):
            role_name = step['role']
            action = step['action']
            if role_name not in self.active_roles:
                print(f"⚠️ ロール '{role_name}' が見つかりません。スキップします。")
                continue
            node_name = f"step_{i}"
            graph.add_node(node_name, make_step_node(i, role_name, action))
            node_names.append(node_name)

        # 並列グループをノードとして追加
        # parallel_steps はフラットなリスト → 全体を1つの並列グループとして実行
        if parallel_groups:
            node_name = "parallel_0"
            graph.add_node(node_name, make_parallel_node(0, parallel_groups))
            node_names.append(node_name)

        if not node_names:
            print("⚠️ 実行可能なステップがありません。")
            return []

        # エントリーポイントと順次エッジを設定
        graph.set_entry_point(node_names[0])
        for k in range(len(node_names) - 1):
            graph.add_edge(node_names[k], node_names[k + 1])
        graph.add_edge(node_names[-1], END)

        app = graph.compile()
        final_state = app.invoke({"topic": topic, "results": [], "step_index": 0})
        results = final_state['results']

        _workflow_elapsed = time.time() - _workflow_start
        print("=" * 60)
        print(f"✅ ワークフロー完了（実時間: {_workflow_elapsed:.2f}秒）")

        session_summary = self.token_tracker.get_session_summary()
        self._finalize_workflow_log(log_filename, session_summary, total_elapsed=_workflow_elapsed)
        print(f"💾 ワークフローログが完成しました: {log_filename}")
        print(f"💰 このセッションのコスト: ${session_summary['total_cost']:.4f}")

        self._save_workflow_final_code(topic, workflow_name)

        return results
    
    def _save_workflow_final_code(self, topic, workflow_name):
        """ワークフロー完了時に最終コードのみを保存"""
        if not CODE_SAVING_ENABLED or not hasattr(self, 'workflow_responses') or not self.workflow_responses:
            return
        
        try:
            # 全レスポンスを統合してコード抽出
            combined_response = "\n\n".join([
                f"=== {resp['role']} ===\n{resp['response']}" 
                for resp in self.workflow_responses
            ])
            
            # 最終コード保存
            code_saver = CodeSaver()
            session_info = code_saver.save_ai_response_complete(
                combined_response, 
                f"workflow_{workflow_name}", 
                f"final_result"
            )
            
            if session_info and session_info.get('saved_files'):
                print(f"\n🎯 最終コード保存完了: {len(session_info['saved_files'])} ファイル")
                print(f"📁 保存先: sandbox/session_{session_info['session_id']}/")
                
                # 実行スクリプトがある場合は案内
                if session_info.get('execution_script'):
                    print(f"🚀 実行方法: cd sandbox/session_{session_info['session_id']} && ./run_all.sh")
            
            # ワークフロー完了後にレスポンス蓄積をクリア
            self.workflow_responses = []
            
        except Exception as save_error:
            print(f"⚠️ 最終コード保存エラー: {save_error}")

    def team_meeting(self, participants, topic, max_rounds=3, interactive=False):
        """チーム会議を実行"""
        if len(participants) < 2:
            print("チーム会議には最低2人の参加者が必要です")
            return
        
        # 存在しない参加者をチェック
        missing_roles = [role for role in participants if role not in self.active_roles]
        if missing_roles:
            print(f"見つからないロール: {', '.join(missing_roles)}")
            return
        
        mode_label = "（インタラクティブモード）" if interactive else ""
        print(f"\n🏢 チーム会議を開始します {mode_label}")
        print(f"参加者: {', '.join(participants)}")
        print(f"議題: {topic}")
        if interactive:
            print("💡 各ラウンド後にあなたの意見を入力できます")
        print("=" * 60)
        
        meeting_log = []
        current_topic = topic
        
        for round_num in range(1, max_rounds + 1):
            print(f"\n📋 Round {round_num}")
            print("-" * 40)
            
            # 並列実行用の関数
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def get_participant_response(participant):
                """参加者の応答を取得"""
                try:
                    # 会議ログを含めた入力を作成
                    input_text = f"会議議題: {topic}\n\n"
                    if meeting_log:
                        input_text += "これまでの議論:\n"
                        # 直近3発言に制限してトークン数を削減
                        input_text += "\n".join(meeting_log[-3:])  
                        input_text += f"\n\n現在の論点: {current_topic}"
                    else:
                        input_text += f"あなたの専門性を活かして、この議題について意見を述べてください: {current_topic}"
                    
                    # 入力長制限 (約4000文字 = 約1000トークン)
                    if len(input_text) > 4000:
                        input_text = input_text[:4000] + "...[省略]"
                    
                    start_time = time.time()
                    response = self.get_response_from_role(participant, input_text)
                    response_time = time.time() - start_time
                    
                    # 改行処理を追加（文字列チェック付き）
                    if isinstance(response, str):
                        formatted_response = response.replace('\\n', '\n')
                    else:
                        formatted_response = str(response) if response else ""
                    
                    return {
                        'participant': participant,
                        'response': response,
                        'formatted_response': formatted_response,
                        'response_time': response_time,
                        'error': None
                    }
                except Exception as e:
                    return {
                        'participant': participant,
                        'response': f"エラー: {e}",
                        'formatted_response': f"エラー: {str(e)[:100]}...",
                        'response_time': 0,
                        'error': str(e)
                    }
            
            # ラウンド内の全参加者に並列でリクエスト
            round_responses = []
            participant_order = {p: i for i, p in enumerate(participants)}  # 元の順序を保持
            
            print(f"⏳ 全員に送信中（レート制限対策で少しずつ）...\n")
            
            with ThreadPoolExecutor(max_workers=len(participants)) as executor:
                # レート制限対策：少しずつずらして送信
                future_to_participant = {}
                for i, p in enumerate(participants):
                    # 0.3秒ずつずらす（レート制限回避）
                    if i > 0:
                        time.sleep(0.3)
                    future_to_participant[executor.submit(get_participant_response, p)] = p
                
                # 完了した順にリアルタイム表示
                completed_count = 0
                for future in as_completed(future_to_participant):
                    completed_count += 1
                    result = future.result()
                    
                    participant = result['participant']
                    
                    if result['error']:
                        print(f"🎭 [{completed_count}/{len(participants)}] {participant} ({result['response_time']:.2f}秒): ❌ {result['formatted_response']}")
                    else:
                        print(f"🎭 [{completed_count}/{len(participants)}] {participant} ({result['response_time']:.2f}秒): {result['formatted_response']}")
                    
                    # 読む時間を確保するため少し待つ
                    if completed_count < len(participants):
                        time.sleep(0.5)
                    
                    # ログに記録（元の順序で保存するため一時保存）
                    log_entry = f"[{participant}] {result['response']}"
                    meeting_log.append(log_entry)
                    round_responses.append((participant_order[participant], result['response']))
            
            # ログの最後の行を改行で区切る
            print()
            
            # インタラクティブモード：ユーザーの意見を受け付ける
            if interactive and round_num < max_rounds:
                print("─" * 60)
                print("💬 あなたの意見を入力してください（スキップは Enter）:")
                try:
                    user_input = input("> ").strip()
                    if user_input:
                        # ユーザーの意見をログに追加
                        log_entry = f"[あなた] {user_input}"
                        meeting_log.append(log_entry)
                        print(f"\n✅ あなたの意見を会議に追加しました")
                        # 次のラウンドではユーザーの意見を踏まえる
                        current_topic = f"参加者の意見「{user_input}」を踏まえて、さらに深く検討してください"
                    else:
                        print("⏭️ スキップしました")
                        current_topic = f"前回の議論を踏まえて、さらに深く検討してください"
                except EOFError:
                    print("\n⏭️ 入力をスキップしました")
                    current_topic = f"前回の議論を踏まえて、さらに深く検討してください"
            else:
                # 議論の方向性を更新（最後の発言を次の論点として使用）
                if round_responses:
                    current_topic = f"前回の議論を踏まえて、さらに深く検討してください"
        
        # 会議の総括（モデレーターロールに依頼）
        summary = ""
        # モデレーターロールを見つける
        moderator_role = None
        for role_name in self.active_roles:
            if self.role_types.get(role_name) == "moderator":
                moderator_role = role_name
                break
        
        if moderator_role:
            print(f"\n📝 会議の総括 ({moderator_role})")
            print("-" * 40)
            summary_input = f"""以下の会議内容を要約し、重要な決定事項とアクションアイテムを整理してください。

【制約】
- 500文字以内でまとめてください
- 箇条書きで簡潔に
- 各参加者の主な意見を反映
- 次のアクションを明確に

議題: {topic}

会議内容:
""" + "\n".join(meeting_log)
            
            print(f"\n⏳ {moderator_role}がまとめを作成中...\n")
            summary = self.get_response_from_role(moderator_role, summary_input)
            if isinstance(summary, str):
                formatted_summary = summary.replace('\\n', '\n')
            else:
                formatted_summary = str(summary) if summary else ""
            print(f"🎭 {moderator_role}: {formatted_summary}")
        
        # Markdownファイルとして保存（モデレーター情報も渡す）
        self.save_meeting_log(topic, participants, meeting_log, summary, moderator_role=moderator_role)
        
        print("=" * 60)
        print("✅ チーム会議終了")
        return meeting_log
    
    def quiz_mode(self, question, max_roles=None):
        """クイズモード - 複数ロールから簡潔な回答を取得"""
        if not self.active_roles:
            print("アクティブなロールがありません。まずロールを追加してください。")
            return
        
        # 使用するロールを決定（最大数制限あり）
        roles_to_use = list(self.active_roles.keys())
        if max_roles and len(roles_to_use) > max_roles:
            roles_to_use = roles_to_use[:max_roles]
        
        print(f"\n❓ クイズ: {question}")
        print("=" * 60)
        
        quiz_responses = []
        response_times = {}  # 各ロールの応答時間を記録
        
        # クイズ専用の汎用プロンプト（複数行質問に対応）
        quiz_prompt = f"""あなたは知識豊富なAIアシスタントです。以下の質問に正確で簡潔に答えてください。

重要な制約:
- 回答は必ず100文字以内にしてください
- 確実な事実のみを述べてください
- 推測や憶測は含めないでください
- 選択肢問題の場合は、記号（A、B、Cなど）と答えを明記してください
- 1つの明確な答えを提供してください

質問: 
{question}"""
        
        # 並列実行用の関数
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def get_response_with_timing(role_name):
            """応答を取得して時間を測定"""
            try:
                start_time = time.time()
                response = self.get_quiz_response(role_name, quiz_prompt)
                end_time = time.time()
                response_time = end_time - start_time
                
                # より厳格な文字数制限（100文字まで）
                if len(response) > 100:
                    response = response[:100] + "..."
                
                if isinstance(response, str):
                    formatted_response = response.replace('\\n', '\n')
                else:
                    formatted_response = str(response) if response else ""
                
                return {
                    'role_name': role_name,
                    'response': response,
                    'formatted_response': formatted_response,
                    'response_time': response_time,
                    'error': None
                }
            except Exception as e:
                return {
                    'role_name': role_name,
                    'response': f"エラー: {e}",
                    'formatted_response': f"エラー: {str(e)[:100]}...",
                    'response_time': 0,
                    'error': str(e)
                }
        
        # 全ロールに並列でリクエストを送信
        print("\n⏳ 全AIに質問を送信中（レート制限対策で少しずつ）...\n")
        
        with ThreadPoolExecutor(max_workers=len(roles_to_use)) as executor:
            # レート制限対策：少しずつずらして送信
            future_to_role = {}
            for i, role in enumerate(roles_to_use):
                # 0.3秒ずつずらす（レート制限回避）
                if i > 0:
                    time.sleep(0.3)
                future_to_role[executor.submit(get_response_with_timing, role)] = role
            
            # 完了した順に結果を表示
            completed_count = 0
            for future in as_completed(future_to_role):
                completed_count += 1
                result = future.result()
                
                role_name = result['role_name']
                response_time = result['response_time']
                formatted_response = result['formatted_response']
                
                response_times[role_name] = response_time
                
                if result['error']:
                    print(f"🎭 [{completed_count}] {role_name} ({response_time:.2f}秒): ❌ {formatted_response}")
                    quiz_responses.append(f"[{role_name}] {result['response']}")
                else:
                    print(f"🎭 [{completed_count}] {role_name} ({response_time:.2f}秒): {formatted_response}")
                    quiz_responses.append(f"[{role_name}] {result['response']}")
                
                # 読む時間を確保するため少し待つ（クイズは短いので0.3秒）
                if completed_count < len(roles_to_use):
                    time.sleep(0.3)
        
        print("=" * 60)
        
        # 応答時間のサマリーを表示
        if response_times:
            print("\n⏱️ 応答時間サマリー:")
            sorted_times = sorted(response_times.items(), key=lambda x: x[1])
            for role_name, resp_time in sorted_times:
                if resp_time > 0:
                    print(f"  🏃 {role_name}: {resp_time:.2f}秒")
                else:
                    print(f"  ❌ {role_name}: エラー")
            print("=" * 60)
        
        # クイズログを保存（応答時間情報も含める）
        self.save_meeting_log(f"クイズ: {question}", roles_to_use, quiz_responses, "", "quiz", response_times)
        
        return quiz_responses, response_times

    def continuous_quiz_mode(self, max_roles=None):
        """連続クイズモード - 複数の質問を連続して処理"""
        if not self.active_roles:
            print("アクティブなロールがありません。まずロールを追加してください。")
            return
        
        print("\n🎯 連続クイズモードに入りました")
        print("使用可能なコマンド:")
        print("  質問文を複数行で入力 (Ctrl+Z/Ctrl+D で質問終了)")
        print("  :single <質問>       - 単一行質問モード")
        print("  :quit または :exit   - クイズモードを終了")
        print("=" * 60)
        
        quiz_count = 0
        all_quiz_logs = []
        
        while True:
            try:
                print("\n❓ 質問を入力してください (Ctrl+Z/Ctrl+D で終了):")
                question_lines = []
                
                # 最初の入力を取得
                try:
                    first_line = input("  > ").strip()
                except EOFError:
                    print("クイズモードを終了します。")
                    break
                except KeyboardInterrupt:
                    print("\n\nクイズモードを終了します。")
                    break
                
                # 特別コマンドのチェック
                if first_line.lower() in [':quit', ':exit']:
                    print("クイズモードを終了します。")
                    break
                
                # 単一行質問モードの場合
                if first_line.startswith(':single '):
                    question = first_line[8:].strip()  # ":single " を除去
                    if not question:
                        print("質問が入力されませんでした。")
                        continue
                # 複数行質問モード（デフォルト）
                else:
                    question_lines.append(first_line)
                    
                    # 残りの行を入力
                    while True:
                        try:
                            line = input("  > ")
                            question_lines.append(line)
                        except EOFError:
                            break
                        except KeyboardInterrupt:
                            print("\n❌ 質問入力がキャンセルされました。")
                            question_lines = []
                            break
                    
                    if not question_lines:
                        print("質問が入力されませんでした。")
                        continue
                    
                    question = '\n'.join(question_lines)
                
                quiz_count += 1
                
                # 個別のクイズを実行
                quiz_result = self.quiz_mode(question, max_roles)
                
                # quiz_modeの戻り値を処理（応答時間情報を含む）
                if isinstance(quiz_result, tuple) and len(quiz_result) == 2:
                    responses, response_times = quiz_result
                else:
                    # 旧バージョンとの互換性のため
                    responses = quiz_result if quiz_result else []
                    response_times = {}
                
                # 全体ログに追加
                all_quiz_logs.append({
                    'question': question,
                    'responses': responses,
                    'response_times': response_times,
                    'quiz_number': quiz_count
                })
                
            except KeyboardInterrupt:
                print("\n\nクイズモードを終了します。")
                break
            except Exception as e:
                print(f"エラーが発生しました: {e}")
        
        # 連続クイズのまとめログを保存
        if all_quiz_logs:
            self.save_continuous_quiz_log(all_quiz_logs)
        
        print(f"✅ 連続クイズモード終了（合計 {quiz_count} 問）")
        
        # パフォーマンス統計を表示
        if quiz_count > 0:
            self.token_tracker.print_performance_report()

    def get_quiz_response(self, role_name, quiz_prompt):
        """クイズ専用のレスポンス取得（履歴に影響しない）"""
        if role_name not in self.active_roles:
            return f"エラー: ロール '{role_name}' は存在しません"
        
        try:
            role_info = self.active_roles[role_name]
            
            # クイズ専用の独立したプロンプトテンプレート
            quiz_template = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate.from_template("あなたは知識豊富で正確なAIアシスタントです。質問に簡潔で正確に答えてください。"),
                HumanMessagePromptTemplate.from_template("{input}")
            ])
            
            # 独立したチェーンを作成（履歴なし）
            quiz_chain = RunnableSequence(
                quiz_template,
                role_info['instance']
            )
            
            # 応答時間の測定開始
            start_time = time.time()
            response = quiz_chain.invoke({"input": quiz_prompt})
            end_time = time.time()
            
            response_time = end_time - start_time
            
            if isinstance(response, AIMessage):
                # クイズモードでは履歴に追加しない
                content = response.content
                if isinstance(content, list):
                    # リストの場合は文字列に変換
                    content = ' '.join(str(item) for item in content)
                
                response_text = str(content) if content else "応答が空でした"
                
                # トークン使用量と応答時間を記録
                model_name = role_info.get('model', 'unknown')
                usage_info = self.token_tracker.add_usage(model_name, quiz_prompt, response_text, response_time)
                
                return response_text
            else:
                return "応答の取得に失敗しました"
                
        except Exception as e:
            error_msg = str(e)
            if "rate_limit_exceeded" in error_msg:
                return f"⚠️ API制限に達しました。しばらく待ってから再試行してください。"
            elif "credit balance is too low" in error_msg:
                return f"⚠️ APIクレジットが不足しています。"
            elif "429" in error_msg:
                return f"⚠️ レート制限エラー: トークン数を削減する必要があります。"
            else:
                return f"エラー: {e}"

    def save_continuous_quiz_log(self, all_quiz_logs):
        """連続クイズログをMarkdownファイルとして保存"""
        if not os.path.exists(MULTI_LOGS_DIR):
            os.makedirs(MULTI_LOGS_DIR)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{MULTI_LOGS_DIR}/{timestamp}_continuous_quiz.md"
        
        roles_used = list(self.active_roles.keys())
        
        # 組織情報を取得
        organization = self.organization_info.get('organization', '不明')
        
        # 参加ロール詳細情報を作成
        role_details = []
        for role_name in roles_used:
            if role_name in self.active_roles:
                role_info = self.active_roles[role_name]
                assistant = role_info.get('assistant', '不明')
                model = role_info.get('model', '不明')
                role_details.append(f"{role_name} ({assistant}:{model})")
            else:
                role_details.append(f"{role_name} (設定なし)")
        
        md_content = f"""# 連続クイズログ

**開催日時**: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}
**組織**: {organization}
**実行モード**: 連続クイズ
**参加ロール**: {', '.join(roles_used)}
**参加ロール詳細**: 
  {chr(10).join([f'  {detail}' for detail in role_details])}
**総質問数**: {len(all_quiz_logs)}

---

"""
        
        # 各クイズをMarkdown形式で整理
        for quiz_data in all_quiz_logs:
            md_content += f"""## クイズ {quiz_data['quiz_number']}

**質問**: 
```
{quiz_data['question']}
```

**回答**:

"""
            # 各ロールの回答を追加
            for i, response in enumerate(quiz_data['responses'], 1):
                if response.startswith('[') and ']' in response:
                    role_end = response.find(']')
                    role_name = response[1:role_end]
                    content = response[role_end + 2:]
                    md_content += f"### {i}. {role_name}\n\n{content}\n\n"
            
            # 応答時間情報を追加（利用可能な場合）
            if 'response_times' in quiz_data and quiz_data['response_times']:
                md_content += "**応答時間**:\n\n"
                md_content += "| ロール | 応答時間 |\n"
                md_content += "|--------|--------|\n"
                
                # 応答時間順にソート
                sorted_times = sorted(quiz_data['response_times'].items(), key=lambda x: x[1])
                for role_name, resp_time in sorted_times:
                    if resp_time > 0:
                        md_content += f"| {role_name} | {resp_time:.2f}秒 |\n"
                    else:
                        md_content += f"| {role_name} | エラー |\n"
                md_content += "\n"
            
            md_content += "---\n\n"
        
        # パフォーマンス統計を追加
        performance_stats = self.token_tracker.get_performance_stats()
        if performance_stats['models']:
            md_content += "## パフォーマンス統計\n\n"
            md_content += f"**総リクエスト数**: {performance_stats['total_requests']}\n\n"
            md_content += "| モデル | リクエスト数 | 平均応答時間 | 処理速度 (tokens/秒) | 総コスト |\n"
            md_content += "|--------|------------|------------|-------------------|--------|\n"
            
            # ソート（平均応答時間順）
            sorted_models = sorted(
                performance_stats['models'].items(), 
                key=lambda x: x[1]['avg_response_time'] if x[1]['avg_response_time'] > 0 else float('inf')
            )
            
            for model_name, data in sorted_models:
                avg_time = f"{data['avg_response_time']:.2f}秒" if data['avg_response_time'] > 0 else "N/A"
                tokens_per_sec = f"{data['tokens_per_second']:.1f}" if data['tokens_per_second'] > 0 else "N/A"
                md_content += f"| {model_name} | {data['requests']} | {avg_time} | {tokens_per_sec} | ${data['total_cost']:.4f} |\n"
            
            md_content += "\n---\n\n"
        
        # 問題別応答時間サマリーを追加
        quiz_response_times = []
        for quiz_data in all_quiz_logs:
            if 'response_times' in quiz_data and quiz_data['response_times']:
                quiz_response_times.append({
                    'quiz_number': quiz_data['quiz_number'],
                    'times': quiz_data['response_times']
                })
        
        if quiz_response_times:
            md_content += "## 📊 問題別応答時間サマリー\n\n"
            
            # 全ロールの名前を取得
            all_roles = set()
            for quiz_time in quiz_response_times:
                all_roles.update(quiz_time['times'].keys())
            all_roles = sorted(list(all_roles))
            
            # テーブルヘッダー
            md_content += "| 問題 | " + " | ".join(all_roles) + " |\n"
            md_content += "|" + "---|" * (len(all_roles) + 1) + "\n"
            
            # 各問題の応答時間を表示
            for quiz_time in quiz_response_times:
                row = f"| Q{quiz_time['quiz_number']} |"
                for role in all_roles:
                    time_val = quiz_time['times'].get(role, 0)
                    if time_val > 0:
                        row += f" {time_val:.2f}秒 |"
                    else:
                        row += " エラー |"
                md_content += row + "\n"
            
            # 平均応答時間
            avg_times = {}
            for role in all_roles:
                times = [qt['times'].get(role, 0) for qt in quiz_response_times if qt['times'].get(role, 0) > 0]
                if times:
                    avg_times[role] = sum(times) / len(times)
                else:
                    avg_times[role] = 0
            
            # 平均行を追加
            avg_row = "| **平均** |"
            for role in all_roles:
                if avg_times[role] > 0:
                    avg_row += f" **{avg_times[role]:.2f}秒** |"
                else:
                    avg_row += " **N/A** |"
            md_content += avg_row + "\n\n---\n\n"
        
        md_content += f"""
*この連続クイズログは MultiRoleChat v{VERSION} により自動生成されました*
"""
        
        # ファイルに保存
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(md_content)
            print(f"💾 連続クイズログを保存しました: {filename}")
        except Exception as e:
            print(f"⚠️ ログ保存エラー: {e}")

    def _initialize_workflow_log(self, log_filename, workflow, topic, workflow_name):
        """ワークフローログファイルのヘッダーを初期化"""
        organization = self.organization_info.get('organization', '不明')
        workflow_title = workflow.get('name', workflow_name)
        workflow_description = workflow.get('description', '説明なし')
        
        # 参加ロール詳細情報を作成（steps / parallel_steps 両対応）
        _steps = workflow.get('steps', []) + workflow.get('parallel_steps', [])
        workflow_participants = [step['role'] for step in _steps]
        role_details = []
        for participant in workflow_participants:
            if participant in self.active_roles:
                role_info = self.active_roles[participant]
                assistant = role_info.get('assistant', '不明')
                model = role_info.get('model', '不明')
                role_details.append(f"{participant} ({assistant}:{model})")
            else:
                role_details.append(f"{participant} (設定なし)")
        
        header_content = f"""# ワークフローログ - {topic}

**開催日時**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}
**組織**: {organization}
**実行モード**: ワークフロー
**ワークフロー名**: {workflow_title}
**トピック**: {topic}
**説明**: {workflow_description}
**反復回数**: 1/1
**参加者**: {', '.join(workflow_participants)}
**参加ロール詳細**: 
{chr(10).join([f'    {detail}' for detail in role_details])}
**推定コスト**: 計算中...

---

## 📋 記録

"""
        
        try:
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(header_content)
        except Exception as e:
            print(f"⚠️ ログ初期化エラー: {e}")

    def _append_step_to_log(self, log_filename, step_number, role_name, action, response, elapsed=None):
        """ワークフローのステップをログファイルに追記"""
        time_label = f"（{elapsed:.2f}秒）" if elapsed is not None else ""
        step_content = f"""### {step_number}. {role_name}{time_label}

**アクション**: {action}

{response}

---

"""
        try:
            with open(log_filename, 'a', encoding='utf-8') as f:
                f.write(step_content)
        except Exception as e:
            print(f"⚠️ ステップログ追記エラー: {e}")

    def _finalize_workflow_log(self, log_filename, session_summary, total_elapsed=None):
        """ワークフローログファイルを完了"""
        elapsed_line = f"\n**実時間**: {total_elapsed:.2f}秒" if total_elapsed is not None else ""
        cost_info = f"""

## 💰 コスト情報

**入力**: {session_summary['total_input_tokens']}tokens
**出力**: {session_summary['total_output_tokens']}tokens
**推定コスト**: ${session_summary['total_cost']:.4f}

---

**実行完了**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}{elapsed_line}
"""
        try:
            # コスト情報を更新（ヘッダーの「計算中...」部分を置換）
            with open(log_filename, 'r', encoding='utf-8') as f:
                content = f.read()
            
            cost_summary = f"**入力**: {session_summary['total_input_tokens']}tokens\n**出力**: {session_summary['total_output_tokens']}tokens\n**推定コスト**: ${session_summary['total_cost']:.4f}"
            content = content.replace("**推定コスト**: 計算中...", cost_summary)
            
            with open(log_filename, 'w', encoding='utf-8') as f:
                f.write(content + cost_info)
                
        except Exception as e:
            print(f"⚠️ ログ完了処理エラー: {e}")

    def save_meeting_log(self, topic, participants, meeting_log, summary="", log_type="meeting", response_times=None, workflow_info=None, moderator_role=None):
        """会議ログをMarkdownファイルとして保存"""
        if not os.path.exists(MULTI_LOGS_DIR):
            os.makedirs(MULTI_LOGS_DIR)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # ワークフロー情報がある場合はファイル名に含める
        if workflow_info and 'name' in workflow_info:
            filename = f"{MULTI_LOGS_DIR}/{timestamp}_{workflow_info['name']}.md"
        else:
            filename = f"{MULTI_LOGS_DIR}/{timestamp}_{log_type}.md"
        
        # Markdownファイルの内容を作成
        log_type_jp = {
            "meeting": "会議ログ",
            "workflow": "ワークフローログ", 
            "conversation": "対話ログ",
            "talk": "会話ログ",
            "quiz": "クイズログ"
        }
        
        # 実行モード情報を作成
        execution_mode_info = []
        if log_type == "workflow":
            execution_mode_info.append("**実行モード**: ワークフロー")
            if workflow_info:
                execution_mode_info.append(f"**ワークフロー名**: {workflow_info.get('display_name', workflow_info.get('name', '不明'))}")
                execution_mode_info.append(f"**トピック**: {topic}")
                if 'description' in workflow_info and workflow_info['description']:
                    execution_mode_info.append(f"**説明**: {workflow_info['description']}")
                if 'iteration_count' in workflow_info:
                    execution_mode_info.append(f"**反復回数**: {workflow_info['iteration_count']}/{workflow_info.get('max_iterations', '不明')}")
                if 'test_results' in workflow_info and workflow_info['test_results'] is not None:
                    status = "合格" if workflow_info['test_results'] else "不合格"
                    execution_mode_info.append(f"**最終結果**: {status}")
            else:
                execution_mode_info.append("**ワークフロー名**: {情報が利用できません}")
        elif log_type == "conversation":
            execution_mode_info.append("**実行モード**: ロール間対話")
            execution_mode_info.append("**対話ペア**: {}, {}".format(participants[0] if len(participants) > 0 else "不明", participants[1] if len(participants) > 1 else "不明"))
        elif log_type == "quiz":
            execution_mode_info.append("**実行モード**: クイズ")
            execution_mode_info.append("**質問**: {topic}")
        elif log_type == "talk":
            execution_mode_info.append("**実行モード**: 個別会話")
            execution_mode_info.append("**相手ロール**: {}".format(participants[1] if len(participants) > 1 else "不明"))
        else:  # meeting
            execution_mode_info.append("**実行モード**: チーム会議")
            execution_mode_info.append("**会議テーマ**: {topic}")
        
        # セッションの使用量サマリーを取得
        session_summary = self.token_tracker.get_session_summary()
        cost_info = f"**入力**: {session_summary['total_input_tokens']}tokens\n**出力**: {session_summary['total_output_tokens']}tokens\n**推定コスト**: ${session_summary['total_cost']:.4f}"
        
        # 組織情報を取得
        organization = self.organization_info.get('organization', '不明')
        
        # 参加ロール詳細情報を作成
        role_details = []
        for participant in participants:
            if participant in self.active_roles:
                role_info = self.active_roles[participant]
                assistant = role_info.get('assistant', '不明')
                model = role_info.get('model', '不明')
                role_details.append(f"{participant} ({assistant}:{model})")
            else:
                role_details.append(f"{participant} (設定なし)")
        
        md_content = f"""# {log_type_jp.get(log_type, "ログ")} - {topic}

**開催日時**: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}
**組織**: {organization}
{chr(10).join(execution_mode_info)}
**参加者**: {', '.join(participants)}
**参加ロール詳細**: 
  {chr(10).join([f'  {detail}' for detail in role_details])}
**推定コスト**: {cost_info}

---

## 📋 {"議事録" if log_type == "meeting" else "記録"}

"""
        
        # クイズの場合は応答時間情報を追加
        if log_type == "quiz" and response_times:
            md_content += "### ⏱️ 応答時間\n\n"
            md_content += "| ロール | 応答時間 |\n"
            md_content += "|--------|--------|\n"
            
            # 応答時間順にソート
            sorted_times = sorted(response_times.items(), key=lambda x: x[1])
            for role_name, resp_time in sorted_times:
                if resp_time > 0:
                    md_content += f"| {role_name} | {resp_time:.2f}秒 |\n"
                else:
                    md_content += f"| {role_name} | エラー |\n"
            
            md_content += "\n---\n\n"
        
        # 各発言をMarkdown形式で整理
        for i, log_entry in enumerate(meeting_log, 1):
            if log_entry.startswith('[') and ']' in log_entry:
                # [ロール名] 発言内容 の形式を解析
                role_end = log_entry.find(']')
                role_name = log_entry[1:role_end]
                content = log_entry[role_end + 2:]  # "] " を除去
                
                md_content += f"### {i}. {role_name}\n\n{content}\n\n---\n\n"
        
        # 総括があれば追加
        if summary:
            moderator_label = f" ({moderator_role})" if moderator_role else ""
            md_content += f"""## 📝 会議総括{moderator_label}

{summary}

---

*このログは MultiRoleChat v{VERSION} により自動生成されました*
"""
        
        # ファイルに保存
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(md_content)
            print(f"💾 会議ログを保存しました: {filename}")
        except Exception as e:
            print(f"⚠️ ログ保存エラー: {e}")

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
                    'fast_model': row.get('fast_model', '').strip()
                }
        print(f"[INFO] AI Assistants設定を {AI_ASSISTANTS_CONFIG_FILE} から読み込みました。")
    except Exception as e:
        print(f"[ERROR] AI Assistants設定ファイルの読み込みに失敗しました: {e}")
        return {}
    
    return ai_assistants

def parse_arguments():
    """コマンドライン引数を解析"""
    parser = argparse.ArgumentParser(
        description="MultiRoleChat - マルチロールAIチャットボット",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python MultiRoleChat.py                    # 対話モードで開始
  python MultiRoleChat.py --demo             # デモ用の事前定義ロールで開始
  python MultiRoleChat.py --scenario debate # 討論シナリオで開始
  python MultiRoleChat.py --org creative_org --workflow creative_brainstorm --topic "AIペット" # 組織ワークフロー実行（推奨）
  python MultiRoleChat.py --org tech_startup                                  # テックスタートアップ組織で対話モード

コマンド（実行中）:
  add <role> <assistant> <model> <prompt>  : 新しいロールを追加
  remove <role>                            : ロールを削除
  list                                     : 現在のロール一覧を表示
  talk <role> <message>                    : 指定ロールと会話
  conversation <role1> <role2> <message>   : ロール間会話を開始
  meeting [-i] [-r N] [役割...] <議題>     : チーム会議を開催（-i: あなたも参加）
  quiz <question>                          : 複数ロールから簡潔回答を取得（並列処理）
  workflow <workflow_name> <topic>         : ワークフローを実行
  cost                                     : セッションコストを表示
  quit                                     : 終了
        """
    )
    
    parser.add_argument("--demo", action="store_true",
                        help="Start with predefined demo roles")
    parser.add_argument("--organization", action="store_true",
                        help="Start with organization roles (CEO, secretary, planner, analyst)")
    parser.add_argument("--org", type=str,
                        help="Specify organization name (e.g., tech_startup, creative_org)")
    parser.add_argument("--workflow", type=str,
                        help="Execute specific workflow (e.g., creative_brainstorm, innovation_challenge)")
    parser.add_argument("--topic", type=str,
                        help="Topic for workflow execution")
    parser.add_argument("--scenario", type=str,
                        help="Start with a predefined scenario (e.g., debate, brainstorm, interview, auto_programming)")
    parser.add_argument("--config", type=str,
                        help="Specify configuration file (legacy format, use --org instead)")
    parser.add_argument("--fast", action="store_true",
                        help="Use fast models for quicker responses")
    parser.add_argument("--version", action="version", version=f"MultiRoleChat v{VERSION}")
    
    return parser.parse_args()

def load_multi_role_config(config_file=None):
    """マルチロール設定をJSONファイルから読み込む（非推奨: --org を使用してください）"""
    if config_file is None:
        print("[WARNING] 設定ファイルが指定されていません。--org オプションの使用を推奨します。")
        return None
        
    if not os.path.exists(config_file):
        print(f"[WARNING] マルチロール設定ファイル '{config_file}' が見つかりません。--org オプションの使用を推奨します。")
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"[INFO] マルチロール設定を {config_file} から読み込みました。")
        return config
    except Exception as e:
        print(f"[ERROR] マルチロール設定ファイルの読み込みに失敗しました: {e}")
        return None

def load_organization_config(org_name):
    """組織設定を読み込む"""
    org_config_path = f"organizations/{org_name}/config.json"
    
    if not os.path.exists(org_config_path):
        print(f"[ERROR] 組織設定ファイル '{org_config_path}' が見つかりません。")
        return None
    
    try:
        with open(org_config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"[INFO] 組織設定を {org_config_path} から読み込みました。")
        return config
    except Exception as e:
        print(f"[ERROR] 組織設定ファイルの読み込みに失敗しました: {e}")
        return None

def load_organization_ai_config(org_config, org_name):
    """組織専用のAI設定を読み込む（設定されている場合）"""
    # 組織設定にai_assistants_configが定義されているかチェック
    if 'ai_assistants_config' not in org_config:
        return None
    
    ai_config_path = org_config['ai_assistants_config']
    
    # 相対パスの場合は組織ディレクトリからの相対パスとして解決
    if not os.path.isabs(ai_config_path):
        ai_config_path = f"organizations/{org_name}/{ai_config_path}"
    
    if not os.path.exists(ai_config_path):
        print(f"[WARNING] 組織専用AI設定ファイル '{ai_config_path}' が見つかりません。デフォルト設定を使用します。")
        return None
    
    try:
        ai_assistants = {}
        with open(ai_config_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                assistant_name = row['assistant_name']
                ai_assistants[assistant_name] = {
                    'module': row['module'],
                    'class': row['class'],
                    'model': row['model'],
                    'fast_model': row.get('fast_model', '').strip()
                }
        print(f"[INFO] 組織専用AI設定を {ai_config_path} から読み込みました。")
        return ai_assistants
    except Exception as e:
        print(f"[ERROR] 組織専用AI設定ファイルの読み込みに失敗しました: {e}")
        return None

def setup_organization_from_config(role_manager, org_config):
    """組織設定からロールを設定"""
    # 組織設定をMultiRoleManagerに保存
    role_manager.organization_config = org_config
    
    roles_to_process = []
    
    # 新形式（roles配列）をチェック
    if 'roles' in org_config:
        roles_to_process = org_config['roles']
    # 旧形式（demo_roles + organization_roles）をチェック
    elif 'demo_roles' in org_config or 'organization_roles' in org_config:
        # 旧形式の場合は両方のロールを統合
        roles_to_process = []
        if 'demo_roles' in org_config:
            roles_to_process.extend(org_config['demo_roles'])
        if 'organization_roles' in org_config:
            roles_to_process.extend(org_config['organization_roles'])
    else:
        print("[ERROR] 組織設定にロール情報がありません。")
        return
    
    org_name = org_config.get('organization', org_config.get('name', 'unknown'))
    print(f"[INFO] 組織 '{org_name}' から {len(roles_to_process)} 個のロールを読み込みます。")
    
    for role_config in roles_to_process:
        try:
            # システムプロンプトファイルのパスを取得
            system_prompt_file = role_config['system_prompt_file']
            
            # パスがすでに organizations/ で始まっている場合はそのまま使用
            # そうでない場合は組織ディレクトリからの相対パスとして解決
            if not system_prompt_file.startswith('organizations/') and not os.path.isabs(system_prompt_file):
                system_prompt_file = f"organizations/{org_name}/{system_prompt_file}"
            
            system_prompt = load_system_prompt_from_file(system_prompt_file)
            if system_prompt:
                # role_typeを取得（デフォルトは"member"）
                role_type = role_config.get('role_type', 'member')
                
                role_manager.add_role(
                    role_config['name'],
                    role_config['assistant'],
                    role_config['model'],
                    system_prompt,
                    source_file=system_prompt_file,
                    role_type=role_type
                )
                
                role_type_label = "👨‍💼(進行役)" if role_type == "moderator" else ""
                print(f"✅ ロール '{role_config['name']}' を追加しました {role_type_label}")
            else:
                print(f"❌ ロール '{role_config['name']}' のシステムプロンプト読み込みに失敗しました")
        except Exception as e:
            print(f"❌ ロール '{role_config['name']}' の設定でエラーが発生しました: {e}")

def execute_workflow(role_manager, org_config, workflow_name, topic):
    """ワークフローを実行（反復機能対応）"""
    if 'workflows' not in org_config or workflow_name not in org_config['workflows']:
        print(f"[ERROR] ワークフロー '{workflow_name}' が見つかりません。")
        available_workflows = list(org_config.get('workflows', {}).keys())
        if available_workflows:
            print("利用可能なワークフロー:")
            for wf in available_workflows:
                print(f"  - {wf}")
        return
    
    workflow = org_config['workflows'][workflow_name]
    workflow_title = workflow.get('name', workflow_name)
    workflow_description = workflow.get('description', '')
    
    # 反復ワークフローかどうかを判定
    is_iterative = workflow.get('max_iterations', 0) > 1 or workflow_name.endswith('_iterative')
    
    if is_iterative:
        print(f"\n🔄 反復ワークフロー実行: {workflow_title}")
        if workflow_description:
            print(f"📝 説明: {workflow_description}")
        print(f"💬 トピック: {topic}")
        max_iter = workflow.get('max_iterations', 5)
        print(f"🔄 最大反復回数: {max_iter}")
        print("=" * 60)
        
        # 反復実行（ログは内部で処理）
        role_manager.execute_iterative_workflow(workflow_name, topic, max_iter)
    else:
        print(f"\n🎭 ワークフロー実行: {workflow_title}")
        if workflow_description:
            print(f"📝 説明: {workflow_description}")
        print(f"💬 トピック: {topic}")
        print("=" * 60)
        
        # 通常実行（ログは内部で処理）
        role_manager.execute_workflow(workflow_name, topic)
    
    # 反復ワークフローの場合は、既にログが保存されているので重複を避ける
    # 通常ワークフローの場合も、role_manager.execute_workflow内でログが保存される


def execute_scenario(role_manager, org_config, scenario_name, topic, max_rounds=3):
    """シナリオを実行"""
    if 'scenarios' not in org_config or scenario_name not in org_config['scenarios']:
        print(f"[ERROR] シナリオ '{scenario_name}' が見つかりません。")
        available_scenarios = list(org_config.get('scenarios', {}).keys())
        if available_scenarios:
            print("利用可能なシナリオ:")
            for sc in available_scenarios:
                print(f"  - {sc}")
        return
    
    scenario = org_config['scenarios'][scenario_name]
    scenario_title = scenario_name
    
    print(f"\n🎭 シナリオ実行: {scenario_title}")
    print(f"💬 トピック: {topic}")
    print("=" * 60)
    
    # ログファイル名を生成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"multi_logs/{timestamp}_{scenario_name}.md"
    
    conversation_log = []
    conversation_log.append(f"# シナリオログ - {scenario_title}")
    conversation_log.append(f"\n**実行日時**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
    
    # 組織情報を取得
    organization = role_manager.organization_info.get('organization', '不明')
    conversation_log.append(f"**組織**: {organization}")
    
    conversation_log.append(f"**実行モード**: シナリオ")
    conversation_log.append(f"**シナリオ名**: {scenario_name}")
    conversation_log.append(f"**トピック**: {topic}")
    
    # 参加ロール詳細情報を作成
    participants = [role_config['name'] for role_config in scenario]
    role_details = []
    for participant in participants:
        if participant in role_manager.active_roles:
            role_info = role_manager.active_roles[participant]
            assistant = role_info.get('assistant', '不明')
            model = role_info.get('model', '不明')
            role_details.append(f"{participant} ({assistant}:{model})")
        else:
            role_details.append(f"{participant} (設定なし)")
    
    conversation_log.append("**参加ロール詳細**: ")
    for detail in role_details:
        conversation_log.append(f"  {detail}")
    
    # コスト情報をプレースホルダーとして追加
    cost_placeholder_index = len(conversation_log)
    conversation_log.append("**推定コスト**: 計算中...")
    
    conversation_log.append("\n---\n")
    conversation_log.append("## 💬 対話\n")
    
    # 参加ロール
    participants = [role_config['name'] for role_config in scenario]
    
    # シナリオの対話を実行
    for round_num in range(1, max_rounds + 1):
        print(f"\n📋 ラウンド {round_num}")
        print("-" * 40)
        
        conversation_log.append(f"### ラウンド {round_num}\n")
        
        for role_config in scenario:
            role_name = role_config['name']
            
            # ロールが存在するかチェック
            if role_name not in role_manager.active_roles:
                print(f"❌ ロール '{role_name}' が見つかりません。スキップします。")
                conversation_log.append(f"❌ **エラー**: ロール '{role_name}' が見つかりません\n")
                continue
            
            # メッセージを構築
            message = f"【シナリオ】{scenario_title}\n\nトピック: {topic}\n\n"
            if round_num > 1:
                message += "これまでの議論を踏まえて、あなたの役割から発言してください。"
            else:
                message += "このトピックについて、あなたの役割の立場から発言してください。"
            
            try:
                response = role_manager.get_response_from_role(role_name, message)
                print(f"💬 {role_name}: {response}")
                conversation_log.append(f"**{role_name}**: {response}\n\n")
            except Exception as e:
                error_msg = f"エラーが発生しました: {e}"
                print(f"❌ {error_msg}")
                conversation_log.append(f"❌ **エラー**: {error_msg}\n\n")
        
        conversation_log.append("---\n\n")
    
    # ログを保存
    try:
        # 最終的なコスト情報を更新
        session_summary = role_manager.token_tracker.get_session_summary()
        cost_info = f"**入力**: {session_summary['total_input_tokens']}tokens\n**出力**: {session_summary['total_output_tokens']}tokens\n**推定コスト**: ${session_summary['total_cost']:.4f}"
        conversation_log[cost_placeholder_index] = cost_info
        
        os.makedirs(os.path.dirname(log_filename), exist_ok=True)
        with open(log_filename, 'w', encoding='utf-8') as f:
            f.write('\n'.join(conversation_log))
        print(f"\n💾 シナリオログを保存しました: {log_filename}")
        print(f"💰 このセッションのコスト: {cost_info}")
    except Exception as e:
        print(f"❌ ログの保存に失敗しました: {e}")
    
    print(f"\n🎉 シナリオ '{scenario_title}' が完了しました！")

def load_system_prompt_from_file(filename):
    """システムプロンプトをファイルから読み込む"""
    if not os.path.exists(filename):
        print(f"[WARNING] システムプロンプトファイル '{filename}' が見つかりません。")
        return None
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"[ERROR] システムプロンプトファイル '{filename}' の読み込みに失敗しました: {e}")
        return None

def setup_demo_roles(role_manager):
    """デモ用のロールを設定"""
    config = load_multi_role_config(role_manager.config_file)
    
    if config and 'demo_roles' in config:
        # 外部設定ファイルからロードする場合
        for role_config in config['demo_roles']:
            try:
                system_prompt_file = role_config['system_prompt_file']
                system_prompt = load_system_prompt_from_file(system_prompt_file)
                if system_prompt:
                    role_manager.add_role(
                        role_config['name'],
                        role_config['assistant'],
                        role_config['model'],
                        system_prompt,
                        source_file=system_prompt_file
                    )
                else:
                    print(f"ロール '{role_config['name']}' のシステムプロンプト読み込みに失敗しました")
            except Exception as e:
                print(f"ロール '{role_config['name']}' の追加に失敗: {e}")
    else:
        # フォールバック: 内蔵設定を使用
        demo_roles = [
            {
                'name': 'プログラマー',
                'assistant': 'ChatGPT',
                'model': 'gpt-5',
                'prompt': 'あなたは経験豊富なプログラマーです。技術的な質問に対して具体的で実践的な回答を提供してください。コード例も積極的に示してください。'
            },
            {
                'name': 'デザイナー',
                'assistant': 'Gemini',
                'model': 'gemini-2.5-pro',
                'prompt': 'あなたはユーザーエクスペリエンスとビジュアルデザインの専門家です。美しく使いやすいデザインについてアドバイスしてください。'
            },
            {
                'name': 'マーケター',
                'assistant': 'ChatGPT',
                'model': 'gpt-5',
                'prompt': 'あなたはマーケティングの専門家です。ビジネス戦略、ブランディング、顧客獲得について具体的なアドバイスを提供してください。'
            }
        ]
        
        for role in demo_roles:
            try:
                role_manager.add_role(
                    role['name'],
                    role['assistant'],
                    role['model'],
                    role['prompt'],
                    source_file="内蔵設定"
                )
            except Exception as e:
                print(f"ロール '{role['name']}' の追加に失敗: {e}")

def setup_scenario_roles_from_org(role_manager, org_config, scenario):
    """組織設定からシナリオ別のロールを設定"""
    if 'scenarios' in org_config and scenario in org_config['scenarios']:
        # 組織固有のシナリオを使用
        print(f"📋 組織 '{org_config.get('organization', 'unknown')}' のシナリオ '{scenario}' を実行します")
        
        for role_config in org_config['scenarios'][scenario]:
            try:
                system_prompt_file = role_config['system_prompt_file']
                
                # パスがすでに organizations/ で始まっている場合はそのまま使用
                # そうでない場合は組織ディレクトリからの相対パスとして解決
                if not system_prompt_file.startswith('organizations/') and not os.path.isabs(system_prompt_file):
                    org_name = org_config.get('organization', 'unknown')
                    system_prompt_file = f"organizations/{org_name}/{system_prompt_file}"
                
                system_prompt = load_system_prompt_from_file(system_prompt_file)
                if system_prompt:
                    role_manager.add_role(
                        role_config['name'],
                        role_config['assistant'],
                        role_config['model'],
                        system_prompt,
                        source_file=system_prompt_file
                    )
                    print(f"✅ シナリオロール '{role_config['name']}' を追加しました")
                else:
                    print(f"❌ ロール '{role_config['name']}' のシステムプロンプト読み込みに失敗しました")
            except Exception as e:
                print(f"❌ ロール '{role_config['name']}' の設定でエラーが発生しました: {e}")
    else:
        # シナリオが見つからない場合
        available_scenarios = list(org_config.get('scenarios', {}).keys()) if 'scenarios' in org_config else []
        print(f"❌ シナリオ '{scenario}' が組織 '{org_config.get('organization', 'unknown')}' で見つかりません。")
        if available_scenarios:
            print(f"📋 利用可能なシナリオ: {', '.join(available_scenarios)}")
        else:
            print("📋 この組織にはシナリオが設定されていません。")
        return False
    return True

def setup_scenario_roles(role_manager, scenario):
    """シナリオ別のロールを設定"""
    config = load_multi_role_config(role_manager.config_file)
    
    if config and 'scenarios' in config and scenario in config['scenarios']:
        # 外部設定ファイルからロードする場合
        for role_config in config['scenarios'][scenario]:
            try:
                system_prompt_file = role_config['system_prompt_file']
                system_prompt = load_system_prompt_from_file(system_prompt_file)
                if system_prompt:
                    role_manager.add_role(
                        role_config['name'],
                        role_config['assistant'],
                        role_config['model'],
                        system_prompt,
                        source_file=system_prompt_file
                    )
                else:
                    print(f"ロール '{role_config['name']}' のシステムプロンプト読み込みに失敗しました")
            except Exception as e:
                print(f"ロール '{role_config['name']}' の追加に失敗: {e}")
    else:
        # フォールバック: 内蔵設定を使用
        scenarios = {
            'debate': [
                {
                    'name': '賛成派',
                    'assistant': 'ChatGPT',
                    'model': 'gpt-5',
                    'prompt': 'あなたは討論の賛成派です。論理的で説得力のある賛成論を展開してください。データや事例を用いて主張を支えてください。'
                },
                {
                    'name': '反対派',
                    'assistant': 'Gemini',
                    'model': 'gemini-2.5-pro',
                    'prompt': 'あなたは討論の反対派です。冷静で論理的な反対論を展開してください。リスクや問題点を指摘し、代替案も提示してください。'
                }
            ],
            'brainstorm': [
                {
                    'name': '創造性重視',
                    'assistant': 'ChatGPT',
                    'model': 'gpt-5',
                    'prompt': 'あなたは創造性を重視する発想者です。斬新で革新的なアイデアを積極的に提案してください。常識にとらわれない視点を大切にしてください。'
                },
                {
                    'name': '実現性重視',
                    'assistant': 'Groq',
                    'model': 'llama-3.3-70b-versatile',
                    'prompt': 'あなたは実現性を重視する現実主義者です。アイデアの実現可能性、コスト、リスクを慎重に評価してください。'
                }
            ],
            'interview': [
                {
                    'name': '面接官',
                    'assistant': 'Gemini',
                    'model': 'gemini-2.5-pro',
                    'prompt': 'あなたは経験豊富な面接官です。候補者のスキル、経験、人格を適切に評価するための質問をしてください。'
                },
                {
                    'name': '候補者',
                    'assistant': 'ChatGPT',
                    'model': 'gpt-5',
                    'prompt': 'あなたは就職面接を受ける候補者です。自分のスキルと経験を的確にアピールし、質問に誠実に答えてください。'
                }
            ]
        }
        
        if scenario in scenarios:
            for role in scenarios[scenario]:
                try:
                    role_manager.add_role(
                        role['name'],
                        role['assistant'],
                        role['model'],
                        role['prompt'],
                        source_file="内蔵シナリオ設定"
                    )
                except Exception as e:
                    print(f"ロール '{role['name']}' の追加に失敗: {e}")

def setup_organization_roles(role_manager):
    """組織ロールを設定"""
    config = load_multi_role_config(role_manager.config_file)
    
    if config and 'organization_roles' in config:
        # 外部設定ファイルからロードする場合
        for role_config in config['organization_roles']:
            try:
                system_prompt_file = role_config['system_prompt_file']
                system_prompt = load_system_prompt_from_file(system_prompt_file)
                if system_prompt:
                    role_manager.add_role(
                        role_config['name'],
                        role_config['assistant'],
                        role_config['model'],
                        system_prompt,
                        source_file=system_prompt_file
                    )
                else:
                    print(f"ロール '{role_config['name']}' のシステムプロンプト読み込みに失敗しました")
            except Exception as e:
                print(f"ロール '{role_config['name']}' の追加に失敗: {e}")
    else:
        print("組織ロール設定が見つかりません")

def parse_command(command):
    """コマンドを解析"""
    parts = command.strip().split()
    if not parts:
        return None, []
    
    cmd = parts[0].lower()
    args = parts[1:]
    return cmd, args

def main():
    print_version_info()
    
    # コマンドライン引数を解析
    args = parse_arguments()
    
    # AI Assistants設定を読み込み
    ai_assistants = load_ai_assistants_config()
    if not ai_assistants:
        print("[ERROR] AI Assistants設定の読み込みに失敗しました。プログラムを終了します。")
        return
    
    # 組織指定の場合の処理
    if args.org:
        org_config = load_organization_config(args.org)
        if not org_config:
            return
        
        # 組織専用のAI設定があるかチェックし、あれば使用
        org_ai_assistants = load_organization_ai_config(org_config, args.org)
        if org_ai_assistants:
            print(f"🎯 組織 '{args.org}' 専用のAI設定を使用します。")
            ai_assistants = org_ai_assistants
        
        # 組織設定に基づいてロール管理システムを初期化
        role_manager = MultiRoleManager(ai_assistants, use_fast=args.fast, organization_name=args.org)
        
        # 組織のロールを設定
        print(f"🏢 組織 '{args.org}' のロールを設定しています...")
        setup_organization_from_config(role_manager, org_config)
        
        # シナリオ実行が指定されている場合
        if args.scenario:
            print(f"🎯 '{args.scenario}' シナリオでロールを設定しています...")
            if not setup_scenario_roles_from_org(role_manager, org_config, args.scenario):
                return  # シナリオ設定失敗時は終了
            # シナリオモードではメインループに入る
        # ワークフロー実行が指定されている場合
        elif args.workflow and args.topic:
            print(f"🎯 ワークフロー '{args.workflow}' を実行しています...")
            execute_workflow(role_manager, org_config, args.workflow, args.topic)
            return
        elif args.workflow:
            print("[ERROR] ワークフロー実行にはトピック (--topic) が必要です。")
            return
        
    else:
        # 古いシステム（非推奨）
        if args.config:
            if not os.path.exists(args.config):
                print(f"[ERROR] 設定ファイル '{args.config}' が見つかりません。")
                print("📢 推奨: --org オプションを使用してください")
                print("利用可能な組織:")
                try:
                    orgs = [d for d in os.listdir('organizations') if os.path.isdir(f'organizations/{d}')]
                    for org in orgs:
                        print(f"  - {org}")
                except FileNotFoundError:
                    print("  organizations/ フォルダが見つかりません")
                return
            
            print(f"⚠️  非推奨: {args.config} (--org オプションの使用を推奨)")
            role_manager = MultiRoleManager(ai_assistants, use_fast=args.fast, config_file=args.config, organization_name=None)
        else:
            print("❌ エラー: 組織 (--org) または設定ファイル (--config) を指定してください")
            print("📢 推奨: --org オプションを使用してください")
            print("利用可能な組織:")
            try:
                orgs = [d for d in os.listdir('organizations') if os.path.isdir(f'organizations/{d}')]
                for org in orgs:
                    print(f"  - {org}")
            except FileNotFoundError:
                print("  organizations/ フォルダが見つかりません")
            return
    
    if args.fast:
        print("🚀 Fast Modelモードが有効です。高速応答を優先します。")
    
    # デモまたはシナリオモードの設定（組織指定以外の場合）
    if not args.org:
        if args.demo:
            print("🎭 デモモードでロールを設定しています...")
            setup_demo_roles(role_manager)
        elif args.organization:
            print("🏢 組織モードでロールを設定しています...")
            setup_organization_roles(role_manager)
        elif args.scenario:
            print(f"🎯 '{args.scenario}' シナリオでロールを設定しています...")
            setup_scenario_roles(role_manager, args.scenario)
    
    print("\n🎭 MultiRoleChat へようこそ！")
    print("使用可能なコマンド:")
    print("  add <role> <assistant> <model> <prompt>  - 新しいロールを追加")
    print("  remove <role>                            - ロールを削除")
    print("  list                                     - 現在のロール一覧を表示")
    print("  debug <role>                             - ロールの詳細設定を表示")
    print("  config                                   - 設定ファイルと組織情報を表示")
    print("  talk <role> <message>                    - 指定ロールと会話")
    print("  conversation <role1> <role2> <message>   - ロール間会話を開始")
    print("  quiz <question>                          - 複数ロールから簡潔回答を取得")
    print("  quiz multiline                           - 複数行質問モード (Ctrl+Z/Ctrl+D で終了)")
    print("  quiz continuous                          - 連続質問モード (デフォルト複数行)")
    print("  quiz multiline continuous                - 複数行連続質問モード")
    print("  workflow <workflow_name> <topic>         - ワークフローを実行")
    print("  scenario <scenario_name> <topic>         - シナリオを実行")
    print("  meeting [-i] [-r N] [role...] <topic>    - チーム会議を開催（-i: インタラクティブ）")
    print("  cost                                     - 現在のセッションコストを表示")
    print("  performance または perf                  - パフォーマンス統計を表示")
    print("  quit                                     - 終了")
    print("-" * 50)
    
    # メインループ
    while True:
        try:
            user_input = input("\n🎭 MultiRoleChat> ").strip()
            
            if not user_input:
                continue
            
            cmd, cmd_args = parse_command(user_input)
            
            if cmd == 'quit' or cmd == 'exit':
                print("MultiRoleChat を終了します。")
                break
            
            elif cmd == 'list':
                role_manager.list_roles()
            
            elif cmd == 'config':
                print(f"\n📋 現在の設定情報:")
                print(f"  設定ファイル: {role_manager.config_file}")
                print(f"  絶対パス: {role_manager.organization_info['config_file_path']}")
                print(f"  検出された組織: {role_manager.organization_info['organization']}")
                print(f"  組織パス: {role_manager.organization_info['organization_path']}")
                print(f"  Fast Mode: {'有効' if role_manager.use_fast else '無効'}")
                print(f"  アクティブロール数: {len(role_manager.active_roles)}")
                
                # AI Assistants設定の概要
                print(f"\n📋 利用可能なAI Assistants:")
                for assistant_name, config in role_manager.ai_assistants.items():
                    print(f"  🤖 {assistant_name}:")
                    print(f"      Module: {config['module']}")
                    print(f"      Class: {config['class']}")
                    print(f"      Default Model: {config['model']}")
                    fast_model = config.get('fast_model', '').strip()
                    if fast_model:
                        print(f"      Fast Model: {fast_model}")
            
            elif cmd == 'debug':
                if len(cmd_args) < 1:
                    print("使用法: debug <role>")
                    continue
                
                role_name = cmd_args[0]
                if role_name in role_manager.active_roles:
                    role_info = role_manager.active_roles[role_name]
                    print(f"\n🔍 ロール '{role_name}' の詳細設定:")
                    print(f"  Assistant: {role_info.get('assistant', 'Unknown')}")
                    print(f"  Model: {role_info.get('model', 'Unknown')}")
                    print(f"  Organization: {role_info.get('organization', 'Unknown')}")
                    print(f"  Config Path: {role_info.get('config_path', 'Unknown')}")
                    print(f"  Source File: {role_info.get('source_file', 'Unknown')}")
                    print(f"  システムプロンプト:")
                    print(f"    {role_info.get('system_prompt', 'Unknown')}")
                    print(f"  インスタンス: {type(role_info.get('instance', 'None'))}")
                    
                    # AI Assistantsの設定も表示
                    assistant_name = role_info.get('assistant', 'Unknown')
                    if assistant_name in role_manager.ai_assistants:
                        ai_config = role_manager.ai_assistants[assistant_name]
                        print(f"  AI Assistant設定:")
                        print(f"    Module: {ai_config.get('module', 'Unknown')}")
                        print(f"    Class: {ai_config.get('class', 'Unknown')}")
                        print(f"    Default Model: {ai_config.get('model', 'Unknown')}")
                        print(f"    Fast Model: {ai_config.get('fast_model', 'None')}")
                else:
                    print(f"⚠️ ロール '{role_name}' は存在しません")
            
            elif cmd == 'add':
                if len(cmd_args) < 4:
                    print("使用法: add <role> <assistant> <model> <prompt>")
                    continue
                
                role_name = cmd_args[0]
                assistant_name = cmd_args[1]
                model_name = cmd_args[2]
                system_prompt = ' '.join(cmd_args[3:])
                
                try:
                    role_manager.add_role(role_name, assistant_name, model_name, system_prompt, source_file="手動追加")
                except Exception as e:
                    print(f"ロール追加エラー: {e}")
            
            elif cmd == 'remove':
                if len(cmd_args) < 1:
                    print("使用法: remove <role>")
                    continue
                
                role_name = cmd_args[0]
                role_manager.remove_role(role_name)
            
            elif cmd == 'talk':
                if len(cmd_args) < 2:
                    print("使用法: talk <role> <message>")
                    continue
                
                role_name = cmd_args[0]
                message = ' '.join(cmd_args[1:])
                
                print(f"\n💬 {role_name} との会話:")
                response = role_manager.get_response_from_role(role_name, message)
                # 改行処理を追加（文字列チェック付き）
                if isinstance(response, str):
                    formatted_response = response.replace('\\n', '\n')
                else:
                    formatted_response = str(response) if response else ""
                print(f"🎭 {role_name}: {formatted_response}")
                
                # 長い応答（500文字以上）の場合は保存を提案
                if len(str(response)) > 500:
                    save_choice = input("\n💾 この会話を保存しますか？ (y/N): ").strip().lower()
                    if save_choice in ['y', 'yes']:
                        talk_log = [f"[User] {message}", f"[{role_name}] {response}"]
                        role_manager.save_meeting_log(f"ユーザーと{role_name}の会話", ["User", role_name], talk_log, "", "talk")
            
            elif cmd == 'conversation':
                if len(cmd_args) < 3:
                    print("使用法: conversation <role1> <role2> <message>")
                    continue
                
                role1 = cmd_args[0]
                role2 = cmd_args[1]
                message = ' '.join(cmd_args[2:])
                
                role_manager.role_to_role_conversation(role1, role2, message)
            
            elif cmd == 'quiz':
                if len(cmd_args) < 1:
                    print("使用法: quiz <question>")
                    print("例: quiz 帰蝶は誰の妻ですか？")
                    print("複数行の質問の場合: quiz multiline (Ctrl+Z または Ctrl+D で終了)")
                    print("連続質問モード: quiz continuous")
                    print("複数行連続質問モード: quiz multiline continuous")
                    continue
                
                # 連続クイズモードの処理
                if cmd_args[0].lower() == 'continuous':
                    role_manager.continuous_quiz_mode(max_roles=None)
                    continue
                
                # 複数行連続クイズモードの処理
                if len(cmd_args) >= 2 and cmd_args[0].lower() == 'multiline' and cmd_args[1].lower() == 'continuous':
                    role_manager.continuous_quiz_mode(max_roles=None)
                    continue
                
                # 複数行質問モードの処理
                if cmd_args[0].lower() == 'multiline' or len(cmd_args) == 1 and cmd_args[0].lower() == 'multiline':
                    print("\n📝 複数行質問モード（終了するには Ctrl+Z (Windows) または Ctrl+D (Mac/Linux) を押してください）:")
                    question_lines = []
                    while True:
                        try:
                            line = input("  > ")
                            question_lines.append(line)
                        except EOFError:
                            # Ctrl+Z (Windows) または Ctrl+D (Mac/Linux) が押された
                            break
                        except KeyboardInterrupt:
                            # Ctrl+C が押された場合はキャンセル
                            print("\n❌ 質問入力がキャンセルされました。")
                            question_lines = []
                            break
                    
                    if not question_lines:
                        print("質問が入力されませんでした。")
                        continue
                    
                    question = '\n'.join(question_lines)
                else:
                    # 単一行質問
                    question = ' '.join(cmd_args)
                
                role_manager.quiz_mode(question, max_roles=None)  # 制限なし（全ロール参加）
            
            elif cmd == 'workflow':
                if len(cmd_args) < 2:
                    print("使用法: workflow <workflow_name> <topic>")
                    # 組織設定からワークフロー一覧を動的に取得
                    _wf_config = None
                    if hasattr(role_manager, 'organization_config') and role_manager.organization_config:
                        _wf_config = role_manager.organization_config
                    elif hasattr(role_manager, 'config_file') and role_manager.config_file:
                        _wf_config = load_multi_role_config(role_manager.config_file)
                    if _wf_config and 'workflows' in _wf_config:
                        _wf_names = list(_wf_config['workflows'].keys())
                        print("利用可能なワークフロー: " + ", ".join(_wf_names))
                    else:
                        print("利用可能なワークフロー: project_planning, product_development, market_research")
                    continue
                
                workflow_name = cmd_args[0]
                topic = ' '.join(cmd_args[1:])
                
                role_manager.execute_workflow(workflow_name, topic)
            
            elif cmd == 'scenario':
                if len(cmd_args) < 2:
                    print("使用法: scenario <scenario_name> <topic>")
                    print("利用可能なシナリオ: 組織設定によって異なります")
                    continue
                
                scenario_name = cmd_args[0]
                topic = ' '.join(cmd_args[1:])
                
                # 組織設定でシナリオ実行（新システム）
                if hasattr(role_manager, 'organization_info') and role_manager.organization_info.get('organization') != 'unknown':
                    print("組織設定からシナリオを実行中...")
                    # TODO: 組織設定を再読み込みしてシナリオ実行
                    print("⚠️ 組織ベースのシナリオ実行は未実装です。旧システムを使用してください。")
                else:
                    # 旧システムでシナリオ実行
                    role_manager.execute_workflow(scenario_name, topic)  # ワークフローとして実行
            
            elif cmd == 'meeting':
                if len(cmd_args) < 1:
                    print("使用法: ")
                    print("  meeting <topic>                          - 全員参加のミーティング（3ラウンド）")
                    print("  meeting -i <topic>                       - インタラクティブモード（あなたも参加）")
                    print("  meeting -r <N> <topic>                   - ラウンド数指定")
                    print("  meeting <role1> <role2> ... <topic>      - 指定ロールのミーティング")
                    print("  meeting -i -r <N> <role1> <role2> <topic> - 全オプション組み合わせ")
                    print("例:")
                    print("  meeting 次四半期の戦略")
                    print("  meeting -i 次四半期の戦略")
                    print("  meeting -r 2 次四半期の戦略")
                    print("  meeting -i -r 5 秘書 企画 マーケター プロジェクト計画")
                    continue
                
                # ラウンド数のデフォルト
                max_rounds = 3
                # インタラクティブモードのデフォルト
                interactive = False
                
                # -i/--interactive オプションをチェック
                if cmd_args[0] in ['-i', '--interactive']:
                    interactive = True
                    cmd_args = cmd_args[1:]  # -i を除去
                    if len(cmd_args) < 1:
                        print("使用法: meeting -i <topic>")
                        print("例: meeting -i 次四半期の戦略")
                        continue
                
                # -r オプションでラウンド数を指定
                if len(cmd_args) > 0 and cmd_args[0] in ['-r', '--rounds']:
                    if len(cmd_args) < 3:
                        print("使用法: meeting -r <ラウンド数> <topic>")
                        print("例: meeting -r 2 次四半期の戦略")
                        continue
                    try:
                        max_rounds = int(cmd_args[1])
                        if max_rounds < 1 or max_rounds > 10:
                            print("ラウンド数は1〜10の範囲で指定してください")
                            continue
                        cmd_args = cmd_args[2:]  # -r と数値を除去
                    except ValueError:
                        print("ラウンド数は数値で指定してください")
                        continue
                
                # ロール指定があるか判定
                # 全引数がアクティブロールに含まれている場合は、最後だけトピック
                # そうでない場合は、全体をトピックとする
                active_role_names = list(role_manager.active_roles.keys())
                
                if len(cmd_args) == 1:
                    # 1つの引数 → トピックのみ、全員参加
                    topic = cmd_args[0]
                    participants = active_role_names
                    print(f"\n👥 全員参加のミーティング（{len(participants)}名、{max_rounds}ラウンド）")
                else:
                    # 複数の引数 → 最後の1つ前までがロール名かチェック
                    potential_roles = cmd_args[:-1]
                    all_are_roles = all(role in active_role_names for role in potential_roles)
                    
                    if all_are_roles and len(potential_roles) >= 2:
                        # ロール指定モード
                        participants = potential_roles
                        topic = cmd_args[-1]
                        print(f"\n👥 指定ロールのミーティング（{len(participants)}名、{max_rounds}ラウンド）")
                    else:
                        # 全体をトピックとして扱い、全員参加
                        topic = ' '.join(cmd_args)
                        participants = active_role_names
                        print(f"\n👥 全員参加のミーティング（{len(participants)}名、{max_rounds}ラウンド）")
                
                role_manager.team_meeting(participants, topic, max_rounds=max_rounds, interactive=interactive)
            
            elif cmd == 'cost':
                session_summary = role_manager.token_tracker.get_session_summary()
                print(f"\n💰 現在のセッションコスト:")
                print(f"  総コスト: ${session_summary['total_cost']:.4f}")
                print(f"  入力トークン: {session_summary['total_input_tokens']:,}")
                print(f"  出力トークン: {session_summary['total_output_tokens']:,}")
                print(f"  総トークン: {session_summary['total_input_tokens'] + session_summary['total_output_tokens']:,}")
                
                if session_summary['model_breakdown']:
                    print(f"\n📊 モデル別内訳:")
                    for model, usage in session_summary['model_breakdown'].items():
                        print(f"  {model}:")
                        print(f"    コスト: ${usage['cost']:.4f}")
                        print(f"    入力: {usage['input_tokens']:,}tokens")
                        print(f"    出力: {usage['output_tokens']:,}tokens")
            
            elif cmd in ['performance', 'perf']:
                role_manager.token_tracker.print_performance_report()
            
            else:
                print(f"不明なコマンド: {cmd}")
                print("'list' でコマンド一覧を確認してください")
        
        except KeyboardInterrupt:
            print("\n\nMultiRoleChat を終了します。")
            break
        except EOFError:
            print("\n\n入力終了により MultiRoleChat を終了します。")
            break
        except Exception as e:
            print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main()
