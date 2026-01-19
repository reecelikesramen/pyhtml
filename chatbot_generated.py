from pyhtml.runtime.page import BasePage
from starlette.responses import Response
import json
import asyncio
from groq import Groq
import os
import sys
import importlib.util
from types import SimpleNamespace
from dotenv import load_dotenv
import asyncio
from typing import List

class IndexPage(BasePage):

    async def _handler_0(self):
        self.new_chat()

    async def _handler_1(self, arg0):
        await self.load_conversation(arg0)

    async def _handler_2(self, arg0):
        await self.start_edit(arg0)

    async def _handler_3(self):
        await self.send_message()
    __routes__ = {'main': '/chatbot', 'conversation': '/chatbot/:id'}
    __path_mode__ = 'dict'
    __route__ = '/chatbot'
    __spa_enabled__ = True
    __sibling_paths__ = ['/chatbot', '/chatbot/:id']
    __file_path__ = '/Users/rholmdahl/projects/pyhtml/demo-app/src/pages/chatbot/index.pyhtml'

    def __init__(self, request, params, query, path=None, url=None):
        super().__init__(request, params, query, path, url)
        self._init_slots()
    dotenv_paths = [os.path.join(os.getcwd(), 'demo-app', '.env'), os.path.join(os.getcwd(), '.env'), os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env') if '__file__' in locals() else '.env']
    for p in dotenv_paths:
        if os.path.exists(p):
            load_dotenv(p)
            break
    possible_paths = [os.path.join(os.getcwd(), 'demo-app', 'src', 'pages', 'chatbot', 'models.py'), os.path.join(os.getcwd(), 'src', 'pages', 'chatbot', 'models.py'), os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models.py') if '__file__' in locals() else 'models.py']
    models_path = None
    for p in possible_paths:
        if os.path.exists(p):
            models_path = p
            break
    if not models_path:
        raise FileNotFoundError(f'Could not find models.py in any of {possible_paths}')
    spec = importlib.util.spec_from_file_location('chatbot_models', models_path)
    chatbot_models = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chatbot_models)
    Session = chatbot_models.Session
    Conversation = chatbot_models.Conversation
    Message = chatbot_models.Message
    API_KEY = os.getenv('GROQ_API_KEY')
    MODEL = os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b')
    conversations = []
    messages = []
    current_conversation_id = None
    current_title = ''
    input_text = ''
    is_loading = False

    async def on_load(self):
        with self.Session() as session:
            convs = session.query(self.Conversation).order_by(self.Conversation.created_at.desc()).all()
            self.conversations = [SimpleNamespace(id=c.id, title=c.title) for c in convs]
        if self.path['conversation']:
            self.current_conversation_id = int(self.params['id'])
            await self.load_conversation_state(self.current_conversation_id)

    async def load_conversation_state(self, conv_id):
        self.current_conversation_id = conv_id
        with self.Session() as session:
            conv = session.query(self.Conversation).filter_by(id=conv_id).first()
            if conv:
                self.current_title = conv.title
                msgs = session.query(self.Message).filter_by(conversation_id=conv_id).order_by(self.Message.created_at.asc()).all()
                self.messages = [SimpleNamespace(id=m.id, role=m.role, content=m.content) for m in msgs]

    async def load_conversation(self, conv_id):
        await self.load_conversation_state(conv_id)

    def new_chat(self):
        self.current_conversation_id = None
        self.messages = []
        self.current_title = 'New Chat'
        self.input_text = ''

    def delete_conversation(self, conv_id):
        with self.Session() as session:
            conv = session.query(self.Conversation).filter_by(id=conv_id).first()
            if conv:
                session.delete(conv)
                session.commit()
        self.conversations = [c for c in self.conversations if c.id != conv_id]
        if self.current_conversation_id == conv_id:
            self.new_chat()

    async def send_message(self):
        text = self.input_text.strip()
        if not text or self.is_loading:
            return
        self.input_text = ''
        self.is_loading = True
        with self.Session() as session:
            if self.current_conversation_id is None:
                title = text[:30] + '...' if len(text) > 30 else text
                new_conv = self.Conversation(title=title)
                session.add(new_conv)
                session.commit()
                self.current_conversation_id = new_conv.id
                self.current_title = title
                self.conversations.insert(0, SimpleNamespace(id=new_conv.id, title=title))
            user_msg = self.Message(conversation_id=self.current_conversation_id, role='user', content=text)
            session.add(user_msg)
            session.commit()
            self.messages.append(SimpleNamespace(id=user_msg.id, role='user', content=text))
            assistant_msg = self.Message(conversation_id=self.current_conversation_id, role='assistant', content='')
            session.add(assistant_msg)
            session.commit()
            assistant_ui_msg = SimpleNamespace(id=assistant_msg.id, role='assistant', content='')
            self.messages.append(assistant_ui_msg)
            client = Groq(api_key=self.API_KEY)
            history = [{'role': m.role, 'content': m.content} for m in self.messages[:-1]]
            try:
                completion = client.chat.completions.create(model=self.MODEL, messages=history, temperature=0.7, max_completion_tokens=4096, top_p=1, stream=True)
                full_content = ''
                for chunk in completion:
                    content = chunk.choices[0].delta.content or ''
                    if content:
                        full_content += content
                        assistant_ui_msg.content = full_content
                        if len(full_content) % 10 == 0:
                            pass
                assistant_msg.content = full_content
                session.merge(assistant_msg)
                session.commit()
            except Exception as e:
                assistant_ui_msg.content = f'Error: {str(e)}'
                assistant_msg.content = f'Error: {str(e)}'
                session.merge(assistant_msg)
                session.commit()
        self.is_loading = False

    async def start_edit(self, msg_idx):
        if msg_idx >= len(self.messages):
            return
        msg_to_edit = self.messages[msg_idx]
        if msg_to_edit.role != 'user':
            return
        self.input_text = msg_to_edit.content
        with self.Session() as session:
            to_delete = self.messages[msg_idx:]
            ids_to_delete = [m.id for m in to_delete if hasattr(m, 'id')]
            if ids_to_delete:
                session.query(self.Message).filter(self.Message.id.in_(ids_to_delete)).delete(synchronize_session=False)
                session.commit()
        self.messages = self.messages[:msg_idx]

    async def _render_template(self):
        parts = []
        import json
        attrs = {}
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<pyhtml-head{''.join(header_parts)}>")
        parts.append('\n    ')
        attrs = {}
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<title{''.join(header_parts)}>")
        parts.append('AI Chatbot - PyHTML')
        parts.append('</title>')
        parts.append('\n    ')
        attrs = {}
        attrs['src'] = 'https://cdn.tailwindcss.com'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<script{''.join(header_parts)}>")
        parts.append('</script>')
        parts.append('\n    ')
        attrs = {}
        attrs['name'] = 'viewport'
        attrs['content'] = 'width=device-width, initial-scale=1'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<meta{''.join(header_parts)}>")
        parts.append('\n')
        parts.append('</pyhtml-head>')
        parts.append('\n')
        attrs = {}
        attrs['class'] = 'flex h-screen bg-[#212121] text-white font-sans overflow-hidden'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n    ')
        attrs = {}
        attrs['class'] = 'w-64 bg-[#171717] flex flex-col border-r border-white/10'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n        ')
        attrs = {}
        attrs['class'] = 'p-4'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n            ')
        attrs = {}
        attrs['class'] = 'w-full flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors border border-white/20 rounded-lg hover:bg-white/5'
        attrs['data-on-click'] = '_handler_0'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<button{''.join(header_parts)}>")
        parts.append('\n                ')
        attrs = {}
        attrs['xmlns'] = 'http://www.w3.org/2000/svg'
        attrs['width'] = '16'
        attrs['height'] = '16'
        attrs['fill'] = 'currentColor'
        attrs['viewbox'] = '0 0 16 16'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<svg{''.join(header_parts)}>")
        parts.append('\n                    ')
        attrs = {}
        attrs['d'] = 'M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3v3a.5.5 0 0 1-1 0v-3h-3a.5.5 0 0 1 0-1h3v-3A.5.5 0 0 1 8 4z'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<path{''.join(header_parts)}>")
        parts.append('</path>')
        parts.append('\n                ')
        parts.append('</svg>')
        parts.append('\n                New Chat\n            ')
        parts.append('</button>')
        parts.append('\n        ')
        parts.append('</div>')
        parts.append('\n        ')
        attrs = {}
        attrs['class'] = 'flex-1 overflow-y-auto px-2 space-y-1'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n            ')
        for conv in self.conversations:
            attrs = {}
            attrs['class'] = 'group flex items-center justify-between px-3 py-2 text-sm rounded-lg cursor-pointer hover:bg-white/5'
            attrs['data-on-click'] = '_handler_1'
            attrs['data-arg-0'] = json.dumps(conv.id)
            _r_val = 'bg-white/10' if self.current_conversation_id == conv.id else ''
            if _r_val is True:
                attrs['class'] = ''
            elif _r_val is not False and _r_val is not None:
                attrs['class'] = str(_r_val)
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<div{''.join(header_parts)}>")
            parts.append('\n                ')
            attrs = {}
            attrs['class'] = 'truncate w-40'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<span{''.join(header_parts)}>")
            parts.append(str(conv.title))
            parts.append('</span>')
            parts.append('\n                ')
            attrs = {}
            attrs['class'] = 'opacity-0 group-hover:opacity-100 p-1 hover:text-red-400'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<button{''.join(header_parts)}>")
            parts.append('\n                    ')
            attrs = {}
            attrs['xmlns'] = 'http://www.w3.org/2000/svg'
            attrs['width'] = '12'
            attrs['height'] = '12'
            attrs['fill'] = 'currentColor'
            attrs['viewbox'] = '0 0 16 16'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<svg{''.join(header_parts)}>")
            parts.append('\n                        ')
            attrs = {}
            attrs['d'] = 'M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<path{''.join(header_parts)}>")
            parts.append('</path>')
            parts.append('\n                        ')
            attrs = {}
            attrs['fill-rule'] = 'evenodd'
            attrs['d'] = 'M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<path{''.join(header_parts)}>")
            parts.append('</path>')
            parts.append('\n                    ')
            parts.append('</svg>')
            parts.append('\n                ')
            parts.append('</button>')
            parts.append('\n            ')
            parts.append('</div>')
        parts.append('\n        ')
        parts.append('</div>')
        parts.append('\n        ')
        attrs = {}
        attrs['class'] = 'p-4 text-xs text-white/40 border-t border-white/10'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n            PyHTML Chatbot v0.1\n        ')
        parts.append('</div>')
        parts.append('\n    ')
        parts.append('</div>')
        parts.append('\n    ')
        attrs = {}
        attrs['class'] = 'flex-1 flex flex-col relative h-screen'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n        ')
        attrs = {}
        attrs['class'] = 'h-14 flex items-center px-6 border-b border-white/10 bg-[#212121]/80 backdrop-blur-md sticky top-0 z-10'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<header{''.join(header_parts)}>")
        parts.append('\n            ')
        attrs = {}
        attrs['class'] = 'text-sm font-semibold truncate'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<h2{''.join(header_parts)}>")
        parts.append('\n                ')
        parts.append(str(self.current_title if self.current_conversation_id else 'AI Assistant'))
        parts.append('\n            ')
        parts.append('</h2>')
        parts.append('\n        ')
        parts.append('</header>')
        parts.append('\n        ')
        attrs = {}
        attrs['id'] = 'chat-container'
        attrs['class'] = 'flex-1 overflow-y-auto scroll-smooth'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n            ')
        attrs = {}
        attrs['class'] = 'max-w-3xl mx-auto py-8'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n                ')
        if not self.messages:
            attrs = {}
            attrs['class'] = 'flex flex-col items-center justify-center min-h-[50vh] text-center px-4'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<div{''.join(header_parts)}>")
            parts.append('\n                    ')
            attrs = {}
            attrs['class'] = 'w-12 h-12 bg-white/10 rounded-full flex items-center justify-center mb-4'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<div{''.join(header_parts)}>")
            parts.append('\n                         ')
            attrs = {}
            attrs['xmlns'] = 'http://www.w3.org/2000/svg'
            attrs['width'] = '24'
            attrs['height'] = '24'
            attrs['fill'] = 'currentColor'
            attrs['viewbox'] = '0 0 16 16'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<svg{''.join(header_parts)}>")
            parts.append('\n                            ')
            attrs = {}
            attrs['d'] = 'M0 2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2h2a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2H2a2 2 0 0 1-2-2V2zm2-1a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H2z'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<path{''.join(header_parts)}>")
            parts.append('</path>')
            parts.append('\n                        ')
            parts.append('</svg>')
            parts.append('\n                    ')
            parts.append('</div>')
            parts.append('\n                    ')
            attrs = {}
            attrs['class'] = 'text-2xl font-bold mb-2'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<h1{''.join(header_parts)}>")
            parts.append('How can I help you today?')
            parts.append('</h1>')
            parts.append('\n                    ')
            attrs = {}
            attrs['class'] = 'text-white/60 text-sm max-w-sm'
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<p{''.join(header_parts)}>")
            parts.append('\n                        Ask anything - from coding questions to creative writing.\n                    ')
            parts.append('</p>')
            parts.append('\n                ')
            parts.append('</div>')
        parts.append('\n                ')
        for idx, msg in enumerate(self.messages):
            attrs = {}
            attrs['class'] = 'group mb-8 px-4 flex gap-4 transition-all duration-300'
            _r_val = 'flex-row-reverse' if msg.role == 'user' else ''
            if _r_val is True:
                attrs['class'] = ''
            elif _r_val is not False and _r_val is not None:
                attrs['class'] = str(_r_val)
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<div{''.join(header_parts)}>")
            parts.append('\n                    ')
            attrs = {}
            attrs['class'] = 'w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold ring-1 ring-white/10'
            _r_val = 'bg-white/10 text-white/80' if msg.role == 'user' else 'bg-blue-600/20 text-blue-400'
            if _r_val is True:
                attrs['class'] = ''
            elif _r_val is not False and _r_val is not None:
                attrs['class'] = str(_r_val)
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<div{''.join(header_parts)}>")
            parts.append('\n                        ')
            parts.append(str(msg.role[0].upper()))
            parts.append('\n                    ')
            parts.append('</div>')
            parts.append('\n                    ')
            attrs = {}
            attrs['class'] = 'flex flex-col gap-2 max-w-[85%]'
            _r_val = 'items-end' if msg.role == 'user' else ''
            if _r_val is True:
                attrs['class'] = ''
            elif _r_val is not False and _r_val is not None:
                attrs['class'] = str(_r_val)
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<div{''.join(header_parts)}>")
            parts.append('\n                        ')
            attrs = {}
            attrs['class'] = 'px-4 py-3 rounded-2xl whitespace-pre-wrap leading-relaxed shadow-sm'
            _r_val = 'bg-[#303030] text-white rounded-tr-none' if msg.role == 'user' else 'bg-transparent text-white/90'
            if _r_val is True:
                attrs['class'] = ''
            elif _r_val is not False and _r_val is not None:
                attrs['class'] = str(_r_val)
            header_parts = []
            for k, v in attrs.items():
                val = str(v).replace('"', '&quot;')
                header_parts.append(f' {k}="{val}"')
            parts.append(f"<div{''.join(header_parts)}>")
            parts.append('\n                            ')
            parts.append(str(msg.content))
            parts.append('\n                            ')
            if self.is_loading and idx == len(self.messages) - 1 and (msg.role == 'assistant') and (not msg.content):
                attrs = {}
                attrs['class'] = 'inline-flex gap-1'
                header_parts = []
                for k, v in attrs.items():
                    val = str(v).replace('"', '&quot;')
                    header_parts.append(f' {k}="{val}"')
                parts.append(f"<span{''.join(header_parts)}>")
                parts.append('\n                                ')
                attrs = {}
                attrs['class'] = 'w-1 h-1 bg-white/50 rounded-full animate-bounce'
                header_parts = []
                for k, v in attrs.items():
                    val = str(v).replace('"', '&quot;')
                    header_parts.append(f' {k}="{val}"')
                parts.append(f"<span{''.join(header_parts)}>")
                parts.append('</span>')
                parts.append('\n                                ')
                attrs = {}
                attrs['class'] = 'w-1 h-1 bg-white/50 rounded-full animate-bounce [animation-delay:0.2s]'
                header_parts = []
                for k, v in attrs.items():
                    val = str(v).replace('"', '&quot;')
                    header_parts.append(f' {k}="{val}"')
                parts.append(f"<span{''.join(header_parts)}>")
                parts.append('</span>')
                parts.append('\n                                ')
                attrs = {}
                attrs['class'] = 'w-1 h-1 bg-white/50 rounded-full animate-bounce [animation-delay:0.4s]'
                header_parts = []
                for k, v in attrs.items():
                    val = str(v).replace('"', '&quot;')
                    header_parts.append(f' {k}="{val}"')
                parts.append(f"<span{''.join(header_parts)}>")
                parts.append('</span>')
                parts.append('\n                            ')
                parts.append('</span>')
            parts.append('\n                        ')
            parts.append('</div>')
            parts.append('\n                        ')
            if msg.role == 'user':
                attrs = {}
                attrs['class'] = 'opacity-0 group-hover:opacity-100 text-[10px] text-white/40 hover:text-white transition-opacity px-2 py-0.5 rounded border border-white/10 hover:bg-white/5'
                attrs['data-on-click'] = '_handler_2'
                attrs['data-arg-0'] = json.dumps(idx)
                header_parts = []
                for k, v in attrs.items():
                    val = str(v).replace('"', '&quot;')
                    header_parts.append(f' {k}="{val}"')
                parts.append(f"<button{''.join(header_parts)}>")
                parts.append('\n                            Edit\n                        ')
                parts.append('</button>')
            parts.append('\n                    ')
            parts.append('</div>')
            parts.append('\n                ')
            parts.append('</div>')
        parts.append('\n            ')
        parts.append('</div>')
        parts.append('\n        ')
        parts.append('</div>')
        parts.append('\n        ')
        attrs = {}
        attrs['class'] = 'w-full bg-gradient-to-t from-[#212121] via-[#212121] to-transparent pt-12 pb-6 px-4'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n            ')
        attrs = {}
        attrs['class'] = 'max-w-3xl mx-auto relative group'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n                ')
        attrs = {}
        attrs['class'] = 'relative flex items-end w-full bg-[#303030] rounded-2xl border border-white/10 shadow-xl focus-within:border-white/20 transition-all duration-300'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n                    ')
        attrs = {}
        attrs['id'] = 'chat-input'
        attrs['placeholder'] = 'Message AI Assistant...'
        attrs['class'] = 'w-full bg-transparent border-none focus:ring-0 resize-none py-4 px-4 text-sm max-h-48 scrollbar-hide'
        attrs['rows'] = '1'
        attrs['value'] = str(self.input_text)
        attrs['data-on-input'] = '_handle_bind_1'
        _r_val = self.is_loading()
        if _r_val is True:
            attrs['disabled'] = ''
        elif _r_val is not False and _r_val is not None:
            attrs['disabled'] = str(_r_val)
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<textarea{''.join(header_parts)}>")
        parts.append('</textarea>')
        parts.append('\n                    ')
        attrs = {}
        attrs['class'] = 'px-2 pb-2'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<div{''.join(header_parts)}>")
        parts.append('\n                         ')
        attrs = {}
        attrs['class'] = 'w-8 h-8 flex items-center justify-center rounded-xl bg-white text-black transition-all hover:bg-white/90 disabled:bg-white/20 disabled:text-white/40 shadow-sm'
        attrs['data-on-click'] = '_handler_3'
        _r_val = self.is_loading or not self.input_text.strip()
        if _r_val is True:
            attrs['disabled'] = ''
        elif _r_val is not False and _r_val is not None:
            attrs['disabled'] = str(_r_val)
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<button{''.join(header_parts)}>")
        parts.append('\n                            ')
        attrs = {}
        attrs['xmlns'] = 'http://www.w3.org/2000/svg'
        attrs['width'] = '16'
        attrs['height'] = '16'
        attrs['fill'] = 'currentColor'
        attrs['viewbox'] = '0 0 16 16'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<svg{''.join(header_parts)}>")
        parts.append('\n                                ')
        attrs = {}
        attrs['d'] = 'M15.854.146a.5.5 0 0 1 .11.54l-5.819 14.547a.75.75 0 0 1-1.329.124l-3.178-4.995L.643 7.184a.75.75 0 0 1 .124-1.33L15.314.037a.5.5 0 0 1 .54.11ZM6.636 10.07l2.761 4.338L14.13 2.576 6.636 10.07Zm6.787-8.201L1.591 6.602l4.339 2.76 7.493-7.493Z'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<path{''.join(header_parts)}>")
        parts.append('</path>')
        parts.append('\n                            ')
        parts.append('</svg>')
        parts.append('\n                        ')
        parts.append('</button>')
        parts.append('\n                    ')
        parts.append('</div>')
        parts.append('\n                ')
        parts.append('</div>')
        parts.append('\n                ')
        attrs = {}
        attrs['class'] = 'mt-3 text-[10px] text-center text-white/30'
        header_parts = []
        for k, v in attrs.items():
            val = str(v).replace('"', '&quot;')
            header_parts.append(f' {k}="{val}"')
        parts.append(f"<p{''.join(header_parts)}>")
        parts.append('\n                    AI may produce inaccurate information. Powered by Groq & GPT-OSS-120B.\n                ')
        parts.append('</p>')
        parts.append('\n            ')
        parts.append('</div>')
        parts.append('\n        ')
        parts.append('</div>')
        parts.append('\n    ')
        parts.append('</div>')
        parts.append('\n')
        parts.append('</div>')
        import json
        if getattr(self, '__spa_enabled__', False):
            sibling_paths = getattr(self, '__sibling_paths__', [])
            parts.append('<script id="_pyhtml_spa_meta" type="application/json">')
            parts.append(json.dumps({'sibling_paths': sibling_paths}))
            parts.append('</script>')
        parts.append('<script src="/_pyhtml/static/pyhtml.min.js"></script>')
        return ''.join(parts)

    def _init_slots(self):
        pass

    async def _handle_bind_1(self, event_data):
        val = event_data.get('value')
        if val is not None:
            self.input_text = val
