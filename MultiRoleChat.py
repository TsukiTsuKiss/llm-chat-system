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

# Version information
VERSION = "1.0.0"
VERSION_DATE = "2025-07-26"

# Configuration files
AI_ASSISTANTS_CONFIG_FILE = "ai_assistants_config.csv"
MULTI_ROLE_CONFIG_FILE = "multi_role_config.json"

# Logs directories
MULTI_LOGS_DIR = "multi_logs"
MULTI_SUMMARIES_DIR = "multi_summaries"

MAX_HISTORY_LENGTH = 10

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
    def __init__(self, max_length=20):
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
    def __init__(self, ai_assistants, use_fast=False):
        self.ai_assistants = ai_assistants
        self.use_fast = use_fast
        self.active_roles = {}
        self.role_prompts = {}
        self.conversation_history = MultiRoleConversationHistory()
    
    def add_role(self, role_name, assistant_name, model_name, system_prompt):
        """新しいロールを追加"""
        if assistant_name not in self.ai_assistants:
            raise ValueError(f"Unknown assistant: {assistant_name}")
        
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
            'instance': assistant_instance
        }
        
        print(f"✅ ロール '{role_name}' を追加しました（{assistant_name}:{model_name}）")
    
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
            print(f"  🎭 {role_name}: {role_info['assistant']}:{role_info['model']}")
            print(f"      システムプロンプト: {role_info['system_prompt'][:50]}...")
    
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
            response = role_info['conversation'].invoke({"input": user_input})
            
            if isinstance(response, AIMessage):
                # 応答を履歴に追加（ロール情報付き）
                self.conversation_history.add_message(HumanMessage(content=user_input), 'user')
                self.conversation_history.add_message(response, role_name)
                return response.content
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
            formatted_response = response.replace('\\n', '\n') if response else response
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

    def execute_workflow(self, workflow_name, topic):
        """ワークフローを実行"""
        config = load_multi_role_config()
        if not config or 'workflows' not in config or workflow_name not in config['workflows']:
            print(f"ワークフロー '{workflow_name}' が見つかりません")
            return
        
        workflow = config['workflows'][workflow_name]
        print(f"\n🔄 ワークフロー '{workflow['name']}' を開始します")
        print(f"トピック: {topic}")
        print("=" * 60)
        
        results = []
        for i, step in enumerate(workflow['steps'], 1):
            role_name = step['role']
            action = step['action']
            
            if role_name not in self.active_roles:
                print(f"⚠️ ロール '{role_name}' が見つかりません。スキップします。")
                continue
            
            print(f"\n📋 Step {i}: {role_name} - {action}")
            print("-" * 40)
            
            # 前のステップの結果を含めた入力を作成
            input_text = f"{topic}\n\n{action}"
            if results:
                input_text += f"\n\n前のステップの結果:\n{chr(10).join(results[-3:])}"  # 最新3件まで
            
            response = self.get_response_from_role(role_name, input_text)
            # 改行処理を追加
            formatted_response = response.replace('\\n', '\n') if response else response
            print(f"🎭 {role_name}: {formatted_response}")
            
            # 結果を保存
            results.append(f"[{role_name}] {response}")
        
        print("=" * 60)
        print("✅ ワークフロー完了")
        
        # ワークフローログを保存
        workflow_participants = [step['role'] for step in workflow['steps']]
        formatted_results = []
        for result in results:
            # [ロール] 応答 形式に統一
            formatted_results.append(result)
        
        self.save_meeting_log(topic, workflow_participants, formatted_results, "", "workflow")
        
        return results
    
    def team_meeting(self, participants, topic, max_rounds=3):
        """チーム会議を実行"""
        if len(participants) < 2:
            print("チーム会議には最低2人の参加者が必要です")
            return
        
        # 存在しない参加者をチェック
        missing_roles = [role for role in participants if role not in self.active_roles]
        if missing_roles:
            print(f"見つからないロール: {', '.join(missing_roles)}")
            return
        
        print(f"\n🏢 チーム会議を開始します")
        print(f"参加者: {', '.join(participants)}")
        print(f"議題: {topic}")
        print("=" * 60)
        
        meeting_log = []
        current_topic = topic
        
        for round_num in range(1, max_rounds + 1):
            print(f"\n📋 Round {round_num}")
            print("-" * 40)
            
            round_responses = []
            for participant in participants:
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
                
                response = self.get_response_from_role(participant, input_text)
                # 改行処理を追加
                formatted_response = response.replace('\\n', '\n') if response else response
                print(f"🎭 {participant}: {formatted_response}")
                
                # ログに記録
                log_entry = f"[{participant}] {response}"
                meeting_log.append(log_entry)
                round_responses.append(response)
            
            # 議論の方向性を更新（最後の発言を次の論点として使用）
            if round_responses:
                current_topic = f"前回の議論を踏まえて、さらに深く検討してください"
        
        # 会議の総括
        summary = ""
        if "秘書" in self.active_roles:
            print(f"\n📝 会議の総括 (秘書)")
            print("-" * 40)
            summary_input = f"以下の会議内容を要約し、重要な決定事項とアクションアイテムを整理してください:\n\n議題: {topic}\n\n会議内容:\n" + "\n".join(meeting_log)
            summary = self.get_response_from_role("秘書", summary_input)
            formatted_summary = summary.replace('\\n', '\n') if summary else summary
            print(f"🎭 秘書: {formatted_summary}")
        
        # Markdownファイルとして保存
        self.save_meeting_log(topic, participants, meeting_log, summary)
        
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
        
        for i, role_name in enumerate(roles_to_use, 1):
            try:
                # クイズモード専用の独立したレスポンス取得
                response = self.get_quiz_response(role_name, quiz_prompt)
                # より厳格な文字数制限（100文字まで）
                if len(response) > 100:
                    response = response[:100] + "..."
                
                formatted_response = response.replace('\\n', '\n') if response else response
                print(f"🎭 [{i}] {role_name}: {formatted_response}")
                
                quiz_responses.append(f"[{role_name}] {response}")
                
            except Exception as e:
                print(f"🎭 [{i}] {role_name}: ❌ エラー - {e}")
                quiz_responses.append(f"[{role_name}] エラー: {e}")
        
        print("=" * 60)
        
        # クイズログを保存
        self.save_meeting_log(f"クイズ: {question}", roles_to_use, quiz_responses, "", "quiz")
        
        return quiz_responses

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
                responses = self.quiz_mode(question, max_roles)
                
                # 全体ログに追加
                all_quiz_logs.append({
                    'question': question,
                    'responses': responses,
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
            
            response = quiz_chain.invoke({"input": quiz_prompt})
            
            if isinstance(response, AIMessage):
                # クイズモードでは履歴に追加しない
                return response.content
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
        filename = f"{MULTI_LOGS_DIR}/continuous_quiz_{timestamp}.md"
        
        roles_used = list(self.active_roles.keys())
        
        md_content = f"""# 連続クイズログ

**開催日時**: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}
**参加ロール**: {', '.join(roles_used)}
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
            
            md_content += "---\n\n"
        
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

    def save_meeting_log(self, topic, participants, meeting_log, summary="", log_type="meeting"):
        """会議ログをMarkdownファイルとして保存"""
        if not os.path.exists(MULTI_LOGS_DIR):
            os.makedirs(MULTI_LOGS_DIR)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{MULTI_LOGS_DIR}/{log_type}_{timestamp}.md"
        
        # Markdownファイルの内容を作成
        log_type_jp = {
            "meeting": "会議ログ",
            "workflow": "ワークフローログ", 
            "conversation": "対話ログ",
            "talk": "会話ログ",
            "quiz": "クイズログ"
        }
        
        md_content = f"""# {log_type_jp.get(log_type, "ログ")} - {topic}

**開催日時**: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}
**参加者**: {', '.join(participants)}

---

## 📋 {"議事録" if log_type == "meeting" else "記録"}

"""
        
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
            md_content += f"""## 📝 会議総括

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

コマンド（実行中）:
  add <role> <assistant> <model> <prompt>  : 新しいロールを追加
  remove <role>                            : ロールを削除
  list                                     : 現在のロール一覧を表示
  talk <role> <message>                    : 指定ロールと会話
  conversation <role1> <role2> <message>   : ロール間会話を開始
  quiz <question>                          : 複数ロールから簡潔回答を取得
  quit                                     : 終了
        """
    )
    
    parser.add_argument("--demo", action="store_true",
                        help="Start with predefined demo roles")
    parser.add_argument("--organization", action="store_true",
                        help="Start with organization roles (CEO, secretary, planner, analyst)")
    parser.add_argument("--scenario", type=str, choices=['debate', 'brainstorm', 'interview'],
                        help="Start with a predefined scenario")
    parser.add_argument("--fast", action="store_true",
                        help="Use fast models for quicker responses")
    parser.add_argument("--version", action="version", version=f"MultiRoleChat v{VERSION}")
    
    return parser.parse_args()

def load_multi_role_config():
    """マルチロール設定をJSONファイルから読み込む"""
    if not os.path.exists(MULTI_ROLE_CONFIG_FILE):
        print(f"[WARNING] マルチロール設定ファイル '{MULTI_ROLE_CONFIG_FILE}' が見つかりません。内蔵設定を使用します。")
        return None
    
    try:
        with open(MULTI_ROLE_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"[INFO] マルチロール設定を {MULTI_ROLE_CONFIG_FILE} から読み込みました。")
        return config
    except Exception as e:
        print(f"[ERROR] マルチロール設定ファイルの読み込みに失敗しました: {e}")
        return None

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
    config = load_multi_role_config()
    
    if config and 'demo_roles' in config:
        # 外部設定ファイルからロードする場合
        for role_config in config['demo_roles']:
            try:
                system_prompt = load_system_prompt_from_file(role_config['system_prompt_file'])
                if system_prompt:
                    role_manager.add_role(
                        role_config['name'],
                        role_config['assistant'],
                        role_config['model'],
                        system_prompt
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
                    role['prompt']
                )
            except Exception as e:
                print(f"ロール '{role['name']}' の追加に失敗: {e}")

def setup_scenario_roles(role_manager, scenario):
    """シナリオ別のロールを設定"""
    config = load_multi_role_config()
    
    if config and 'scenarios' in config and scenario in config['scenarios']:
        # 外部設定ファイルからロードする場合
        for role_config in config['scenarios'][scenario]:
            try:
                system_prompt = load_system_prompt_from_file(role_config['system_prompt_file'])
                if system_prompt:
                    role_manager.add_role(
                        role_config['name'],
                        role_config['assistant'],
                        role_config['model'],
                        system_prompt
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
                        role['prompt']
                    )
                except Exception as e:
                    print(f"ロール '{role['name']}' の追加に失敗: {e}")

def setup_organization_roles(role_manager):
    """組織ロールを設定"""
    config = load_multi_role_config()
    
    if config and 'organization_roles' in config:
        # 外部設定ファイルからロードする場合
        for role_config in config['organization_roles']:
            try:
                system_prompt = load_system_prompt_from_file(role_config['system_prompt_file'])
                if system_prompt:
                    role_manager.add_role(
                        role_config['name'],
                        role_config['assistant'],
                        role_config['model'],
                        system_prompt
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
    
    # AI Assistants設定を読み込み
    ai_assistants = load_ai_assistants_config()
    if not ai_assistants:
        print("[ERROR] AI Assistants設定の読み込みに失敗しました。プログラムを終了します。")
        return
    
    # コマンドライン引数を解析
    args = parse_arguments()
    
    # マルチロール管理システムを初期化
    role_manager = MultiRoleManager(ai_assistants, use_fast=args.fast)
    
    if args.fast:
        print("🚀 Fast Modelモードが有効です。高速応答を優先します。")
    
    # デモまたはシナリオモードの設定
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
    print("  talk <role> <message>                    - 指定ロールと会話")
    print("  conversation <role1> <role2> <message>   - ロール間会話を開始")
    print("  quiz <question>                          - 複数ロールから簡潔回答を取得")
    print("  quiz multiline                           - 複数行質問モード (Ctrl+Z/Ctrl+D で終了)")
    print("  quiz continuous                          - 連続質問モード (デフォルト複数行)")
    print("  quiz multiline continuous                - 複数行連続質問モード")
    print("  workflow <workflow_name> <topic>         - ワークフローを実行")
    print("  meeting <role1> <role2> ... <topic>      - チーム会議を開催")
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
            
            elif cmd == 'add':
                if len(cmd_args) < 4:
                    print("使用法: add <role> <assistant> <model> <prompt>")
                    continue
                
                role_name = cmd_args[0]
                assistant_name = cmd_args[1]
                model_name = cmd_args[2]
                system_prompt = ' '.join(cmd_args[3:])
                
                try:
                    role_manager.add_role(role_name, assistant_name, model_name, system_prompt)
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
                # 改行処理を追加
                formatted_response = response.replace('\\n', '\n') if response else response
                print(f"🎭 {role_name}: {formatted_response}")
                
                # 長い応答（500文字以上）の場合は保存を提案
                if len(response) > 500:
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
                    role_manager.continuous_quiz_mode(max_roles=5)
                    continue
                
                # 複数行連続クイズモードの処理
                if len(cmd_args) >= 2 and cmd_args[0].lower() == 'multiline' and cmd_args[1].lower() == 'continuous':
                    role_manager.continuous_quiz_mode(max_roles=5)
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
                
                role_manager.quiz_mode(question, max_roles=5)  # 最大5ロールまで
            
            elif cmd == 'workflow':
                if len(cmd_args) < 2:
                    print("使用法: workflow <workflow_name> <topic>")
                    print("利用可能なワークフロー: project_planning, product_development, market_research")
                    continue
                
                workflow_name = cmd_args[0]
                topic = ' '.join(cmd_args[1:])
                
                role_manager.execute_workflow(workflow_name, topic)
            
            elif cmd == 'meeting':
                if len(cmd_args) < 3:
                    print("使用法: meeting <role1> <role2> [<role3> ...] <topic>")
                    continue
                
                # 最後の引数をトピックとして扱い、それ以外を参加者とする
                participants = cmd_args[:-1]
                topic = cmd_args[-1]
                
                role_manager.team_meeting(participants, topic)
            
            else:
                print(f"不明なコマンド: {cmd}")
                print("'list' でコマンド一覧を確認してください")
        
        except KeyboardInterrupt:
            print("\n\nMultiRoleChat を終了します。")
            break
        except Exception as e:
            print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main()
