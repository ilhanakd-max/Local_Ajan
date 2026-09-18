import re
import json
from typing import Optional
from lokal_ajan.agent.parser import extract_tool_call, extract_all_tool_calls
from lokal_ajan.agent.history import ChatHistory
from lokal_ajan.agent.prompt import get_system_prompt
from lokal_ajan.agent.thinking import filter_thinking_stream
from lokal_ajan.tools.registry import registry
from lokal_ajan.tools import fs_tools, git_tools  # noqa: F401
from lokal_ajan.llm.model_profiles import ModelProfile
from lokal_ajan.llm.ollama_client import chat_stream as ollama_chat_stream, OllamaConnectionError
from lokal_ajan.llm.openrouter_client import chat_stream as openrouter_chat_stream, OpenRouterConnectionError
from lokal_ajan.llm.ninerouter_client import chat_stream as ninerouter_chat_stream, NineRouterConnectionError
from lokal_ajan.llm.groq_client import chat_stream as groq_chat_stream, GroqConnectionError
from lokal_ajan.agent.context import truncate_tool_output, prepare_context
from rich.console import Console

console = Console()

class AgentLoop:
    def __init__(self, model_name: str, profile: ModelProfile, host: str, workdir: str, config: dict, worker_model: str = None, auto_confirm: bool = True, gpu_mode: bool = False, ponytail_enabled: bool = False, session_name: str = "default"):
        self.model_name = model_name
        self.profile = profile
        self.host = host
        self.workdir = workdir
        self.history = ChatHistory()
        self.config = config
        self.worker_model = worker_model
        self.auto_confirm = auto_confirm
        self.gpu_mode = gpu_mode
        self.ponytail_enabled = ponytail_enabled
        self.session_name = session_name
        self._last_call_key = None
        self._last_call_success = False

        
        # Initialize shell tool with workdir, and ensure existing tool instance has updated workdir
        from lokal_ajan.tools.shell_tool import RunShellTool
        shell_tool = registry.get_tool("run_shell")
        if not shell_tool:
            shell_tool = RunShellTool(workdir=self.workdir)
            registry.register(shell_tool)
        else:
            shell_tool.workdir = self.workdir

        # Initialize tools schema
        self.tools_schema = registry.get_all_schemas()


        self.delegate_tool = None
        if self.worker_model:
            self._ensure_delegate_tool()

    def _ensure_delegate_tool(self):
        if self.delegate_tool is not None:
            return
            
        from pydantic import BaseModel, Field
        from lokal_ajan.tools.base import BaseTool
        import os
        
        class DelegateTaskArgs(BaseModel):
            task: str = Field(description="The complex coding or file operation task to delegate to the worker model.")
            
        class DelegateTaskTool(BaseTool):
            name = "delegate_task"
            description = "Delegate a task to the worker model. Useful for complex coding or running shell commands."
            args_schema = DelegateTaskArgs
            requires_confirm = False
            
            def __init__(self, parent_agent):
                self.parent_agent = parent_agent
                
            def _snapshot_files(self) -> set:
                """Set of absolute paths currently present in the workdir."""
                files = set()
                workdir = self.parent_agent.workdir
                if os.path.isdir(workdir):
                    for root, _dirs, fnames in os.walk(workdir):
                        for fn in fnames:
                            files.add(os.path.normpath(os.path.join(root, fn)))
                return files
            
            def _worker_note(self, worker) -> str:
                """Returns the worker's final assistant message (skipping raw tool-call text)."""
                messages = worker.history.get_messages()
                for msg in reversed(messages):
                    if msg["role"] == "assistant":
                        content = (msg.get("content") or "").strip()
                        if content and "<tool_call>" not in content:
                            return content[:2000]
                return "İşçi model yanıt döndürmedi."
            
            def run(self, task: str):
                from lokal_ajan.llm.model_profiles import get_profile_for_model
                console.print(f"\n[bold magenta]🛠️ İşçi Ajan Başlıyor ({self.parent_agent.worker_model})[/bold magenta]")
                console.print(f"[dim]Görev: {task}[/dim]\n")

                max_attempts = self.parent_agent.config.worker_max_retries
                worker = None

                for attempt in range(max_attempts + 1):
                    worker_profile = get_profile_for_model(self.parent_agent.worker_model, ollama_host=self.parent_agent.host)
                    if self.parent_agent.gpu_mode and worker_profile.num_ctx > 8192:
                        worker_profile = worker_profile.model_copy(update={"num_ctx": 8192})

                    worker = AgentLoop(
                        model_name=self.parent_agent.worker_model,
                        profile=worker_profile,
                        host=self.parent_agent.host,
                        workdir=self.parent_agent.workdir,
                        config=self.parent_agent.config,
                        auto_confirm=True,  # Orkestratör modunda işçi ajan her zaman otomatik onay
                        gpu_mode=self.parent_agent.gpu_mode,
                        ponytail_enabled=self.parent_agent.ponytail_enabled,
                    )


                    before = self._snapshot_files()
                    try:
                        worker_ok = worker.run_step(task)
                    except Exception as e:
                        console.print(f"[bold red]İşçi çalışırken hata: {e}[/bold red]")
                        return f"İşçi model çalışırken hata oluştu: {e}"
                    after = self._snapshot_files()
                    created = sorted(after - before)
                    modified = sorted(
                        p for p in (after & before)
                        if p not in created
                    )

                    note = self._worker_note(worker)

                    # Başarı: yeni/değiştirilmiş dosya var VEYA worker
                    # açıkça bir eylem gerçekleştirdiğini bildirdi.
                    if created or modified:
                        summary = []
                        if created:
                            summary.append(
                                "Oluşturulan dosyalar:\n"
                                + "\n".join(f"  - {c}" for c in created)
                            )
                        if modified:
                            summary.append(
                                "Değiştirilen dosyalar:\n"
                                + "\n".join(f"  - {m}" for m in modified)
                            )
                        return (
                            "İşçi model görevi tamamladı.\n"
                            + "\n".join(summary)
                            + f"\nİşçi notu:\n{note}"
                        )

                    if attempt < max_attempts:
                        console.print(
                            f"[bold red]⚠ İşçi hiçbir dosya oluşturmadı/değiştirmedi "
                            f"({attempt + 1}/{max_attempts}). "
                            f"İşçiye görev yeniden zorla veriliyor...[/bold red]"
                        )
                        task = (
                            f"Önceki denemende hiçbir dosya oluşturulmadı. "
                            f"Dosyaları MUTLAKA oluşturmalısın: kodu sadece göstermek yetmez, "
                            f"write_file aracını kullanarak dosyaları kaydet. Görev: {task}"
                        )

                note = self._worker_note(worker) if worker else "işçi başlatılamadı"
                return (
                    f"⚠ İşçi model görevi tamamlayamadı: {max_attempts + 1} denemede "
                    f"hiçbir dosya oluşturulmadı/değiştirmedi. Son işçi notu:\n{note}"
                )
        
        self.delegate_tool = DelegateTaskTool(self)
        self.tools_schema = [
            t for t in self.tools_schema 
            if t.get("name") not in ("write_file", "edit_file", "run_shell")
        ]
        self.tools_schema.append(self.delegate_tool.get_schema())

        # Set system prompt
        is_orch = bool(self.worker_model)
        sys_prompt = get_system_prompt(self.profile.prompt_level, self.tools_schema, is_orchestrator=is_orch, workdir=self.workdir, ponytail_enabled=self.ponytail_enabled)
        self.history.add_message("system", sys_prompt)

    def reset_session(self):
        """
        Clears conversation history and re-initializes system prompt.
        Also deletes persisted session file.
        """
        self.history.clear()
        is_orch = bool(self.worker_model)
        sys_prompt = get_system_prompt(self.profile.prompt_level, self.tools_schema, is_orchestrator=is_orch, workdir=self.workdir, ponytail_enabled=self.ponytail_enabled)
        self.history.add_message("system", sys_prompt)
        self._last_call_key = None
        self._last_call_success = False
        try:
            from lokal_ajan.agent.session import delete_session
            delete_session(self.workdir, self.session_name)
        except Exception:
            pass

    def load_session_data(self, messages: list):
        """
        Loads messages from a saved session. Keeps the system prompt appropriate
        for the current model while restoring all user/assistant/tool messages.
        """
        self.history.clear()
        is_orch = bool(self.worker_model)
        sys_prompt = get_system_prompt(self.profile.prompt_level, self.tools_schema, is_orchestrator=is_orch, workdir=self.workdir, ponytail_enabled=self.ponytail_enabled)
        self.history.add_message("system", sys_prompt)
        for m in messages:
            if m.get("role") != "system":
                self.history.add_message(m["role"], m["content"])

    def save_current_session(self):
        """Persists the current conversation state to disk."""
        if not self.session_name:
            return
        try:
            from lokal_ajan.agent.session import save_session
            save_session(self.workdir, self.history.get_messages(), self.model_name, self.session_name)
        except Exception:
            pass

    def update_model(self, new_model: str, new_profile: ModelProfile):
        """
        Updates the active model, profile, and synchronizes the system prompt.
        Preserves conversation history across model changes.
        """
        self.model_name = new_model
        self.profile = new_profile
        is_orch = bool(self.worker_model)
        sys_prompt = get_system_prompt(self.profile.prompt_level, self.tools_schema, is_orchestrator=is_orch, workdir=self.workdir, ponytail_enabled=self.ponytail_enabled)
        messages = self.history.get_messages()
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = sys_prompt
        else:
            self.history.messages.insert(0, {"role": "system", "content": sys_prompt})
        self.save_current_session()

    def update_worker_model(self, new_worker_model: Optional[str]):
        """Updates the worker model for orchestrator mode and synchronizes the system prompt."""
        self.worker_model = new_worker_model
        is_orch = bool(self.worker_model)
        sys_prompt = get_system_prompt(self.profile.prompt_level, self.tools_schema, is_orchestrator=is_orch, workdir=self.workdir, ponytail_enabled=self.ponytail_enabled)
        messages = self.history.get_messages()
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = sys_prompt
        else:
            self.history.messages.insert(0, {"role": "system", "content": sys_prompt})
        
        # If orchestrator mode just enabled, ensure delegate_tool is in schema
        if is_orch:
            self._ensure_delegate_tool()
            self.tools_schema = registry.get_all_schemas()
            self.tools_schema = [
                t for t in self.tools_schema 
                if t.get("name") not in ("write_file", "edit_file", "run_shell")
            ]
            self.tools_schema.append(self.delegate_tool.get_schema())
        else:
            # Rebuild without delegate tool
            self.tools_schema = registry.get_all_schemas()

        # Rebuild system prompt with updated tools schema
        sys_prompt = get_system_prompt(self.profile.prompt_level, self.tools_schema, is_orchestrator=is_orch, workdir=self.workdir, ponytail_enabled=self.ponytail_enabled)
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = sys_prompt
        
        self.save_current_session()

    def toggle_ponytail(self, state: bool):
        """
        Enables or disables ponytail mode and updates the system prompt.
        """
        if self.ponytail_enabled == state:
            return False
        
        self.ponytail_enabled = state
        is_orch = bool(self.worker_model)
        sys_prompt = get_system_prompt(self.profile.prompt_level, self.tools_schema, is_orchestrator=is_orch, workdir=self.workdir, ponytail_enabled=self.ponytail_enabled)
        messages = self.history.get_messages()
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = sys_prompt
        else:
            self.history.messages.insert(0, {"role": "system", "content": sys_prompt})
        return True

    def _handle_batch_write(self, args: dict) -> str:
        """
        Writes multiple files extracted from the model's code blocks
        (parser fallback `_write_multiple`). Asks for a single confirmation.
        """
        from lokal_ajan.tools.fs_tools import WriteFileTool
        from lokal_ajan.safety.confirm import request_confirmation
        from lokal_ajan.safety.sandbox import get_safe_path

        files = args.get("files") or []
        valid = [(p, c) for p, c in files if isinstance(p, str) and isinstance(c, str)]

        names = ", ".join(p for p, _ in valid) or "(boş)"
        if not request_confirmation("write_file (toplu)", {"path": f"{len(valid)} dosya: {names}"}, auto_confirm=self.auto_confirm):
            self.history.add_message("user", "Kullanıcı toplu dosya yazma işlemini reddetti.")
            return "Toplu dosya yazma kullanıcı tarafından reddedildi."

        written, errors = [], []
        with console.status(f"[bold yellow]⚙️ {len(valid)} dosya kaydediliyor...[/bold yellow]", spinner="dots"):
            for path, content in valid:
                try:
                    safe = get_safe_path(path, self.workdir)
                    WriteFileTool().run(safe, content)
                    written.append(path)
                except Exception as e:
                    errors.append(f"{path}: {e}")

        result = f"{len(written)} dosya kaydedildi: {', '.join(written)}"
        if errors:
            result += f"\nHatalar: {'; '.join(errors)}"
        self.history.add_message("user", f"Araç '_write_multiple' çalıştı ve şu sonucu döndürdü:\n{result}")
        console.print(f"[dim]Tool Sonucu:\n{result}[/dim]")
        return result

    def run_step(self, user_input: str) -> bool:
        """
        Runs one cycle: sends user input to LLM, streams output, detects tool call.
        If tool call detected, executes it and loops until the LLM replies to the user.
        Returns False if user typed 'exit', True otherwise.
        """
        cmd = user_input.strip().lower()
        if cmd in ("exit", "quit", "/exit", "/quit", "q", "/q"):
            return False
            
        self.history.add_message("user", user_input)
        self._last_call_key = None
        self._last_call_success = False
        step_executed_calls: dict = {}
        
        step_count = 0
        max_steps = self.config.max_steps
        parse_fail_count = 0

        
        while step_count < max_steps:
            console.print("[bold green]Ajan:[/bold green] ", end="")
            
            full_response = ""
            options = {
                "num_ctx": self.profile.num_ctx,
                "temperature": self.profile.temperature,
                "repeat_penalty": self.profile.repeat_penalty,
            }
            # Qwen3 gibi hibrit-düşünme destekleyen modellerde thinking'i
            # API seviyesinde kapat (parser + stream filter zaten ek bir
            # güvenlik katmanı olarak <think> bloklarını süzüyor).
            think = (not self.profile.disable_thinking) if self.profile.supports_think_control else None
            
            messages_to_send = prepare_context(self.history.get_messages(), self.profile.num_ctx)
            
            try:
                if self.model_name.startswith("openrouter/"):
                    raw_stream = openrouter_chat_stream(
                        messages=messages_to_send,
                        model=self.model_name,
                        api_key=self.config.openrouter_api_key,
                        options=options,
                    )
                elif self.model_name.startswith("ninerouter/"):
                    raw_stream = ninerouter_chat_stream(
                        messages=messages_to_send,
                        model=self.model_name,
                        api_key=self.config.ninerouter_api_key,
                        host=self.config.ninerouter_host,
                        options=options,
                    )
                elif self.model_name.startswith("groq/"):
                    raw_stream = groq_chat_stream(
                        messages=messages_to_send,
                        model=self.model_name,
                        api_key=self.config.groq_api_key,
                        options=options,
                    )
                else:
                    raw_stream = ollama_chat_stream(
                        messages=messages_to_send, 
                        model=self.model_name,
                        host=self.host,
                        options=options,
                        think=think,
                        timeout=getattr(self.config, "ollama_timeout", None),
                    )
                
                printed_len = 0
                token_count = 0
                in_tool_mode = False
                
                tool_marker_re = re.compile(
                    r"(<\s*/?\s*t\s*o\s*o\s*l|<tool_call|<tool_|<\|tool_call_start|<function[=\s]|<delegate_task|<write_file|```(?:json)?\s*\{|\[(?:write_file|read_file|edit_file|list_dir|glob|grep|git_status|git_diff|run_shell|delegate_task)\()",
                    re.IGNORECASE,
                )

                # --- Streaming Loop ---
                import sys as _sys
                is_tty = hasattr(_sys.stdout, "isatty") and _sys.stdout.isatty()
                spinner_active = False

                for chunk in filter_thinking_stream(raw_stream):
                    full_response += chunk
                    token_count += 1

                    m = tool_marker_re.search(full_response)
                    if m:
                        # Tool-call marker geldi: henüz yazılmamış önceki metni bas
                        cut_index = m.start()
                        if printed_len < cut_index:
                            pending = full_response[printed_len:cut_index]
                            if pending:
                                if spinner_active:
                                    if is_tty:
                                        _sys.stdout.write("\r\033[K")
                                        _sys.stdout.flush()
                                    else:
                                        console.print()
                                    spinner_active = False
                                console.print(pending, end="")
                                printed_len = cut_index

                        if not in_tool_mode:
                            in_tool_mode = True
                            if printed_len > 0 and not full_response[:printed_len].endswith("\n"):
                                console.print()

                        # Terminal spinner
                        spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
                        sp = spinner_chars[token_count % len(spinner_chars)]
                        if is_tty:
                            _sys.stdout.write(f"\r\033[K  {sp} \033[1;36m⚡ Kod / Araç çağrısı üretiliyor ({token_count} parça)...\033[0m")
                            _sys.stdout.flush()
                        else:
                            if not spinner_active or token_count % 30 == 0:
                                console.print(f"  {sp} [bold cyan]⚡ Kod / Araç çağrısı üretiliyor ({token_count} parça)...[/bold cyan]")
                        spinner_active = True

                    else:
                        # Normal metin: tampon kontrolü yap (yarım tag sızıntısını engelle)
                        tail = full_response[printed_len:]
                        partial_tag_match = re.search(
                            r"(<\s*/?\s*t[a-zA-Z0-9_\s]*|<tool_?[a-zA-Z0-9_]*|<\|tool_?[a-zA-Z0-9_]*|<function[a-zA-Z0-9_]*|\[(?:delegate|write|read|edit|list|glob|grep|git|run)[a-zA-Z0-9_]*)$",
                            tail,
                            re.IGNORECASE,
                        )
                        if partial_tag_match and (len(tail) - partial_tag_match.start()) < 35:
                            safe_len = printed_len + partial_tag_match.start()
                            if safe_len > printed_len:
                                safe_tail = full_response[printed_len:safe_len]
                                if spinner_active:
                                    if is_tty:
                                        _sys.stdout.write("\r\033[K")
                                        _sys.stdout.flush()
                                    else:
                                        console.print()
                                    spinner_active = False
                                console.print(safe_tail, end="")
                                printed_len = safe_len
                        else:
                            if tail:
                                if spinner_active:
                                    if is_tty:
                                        _sys.stdout.write("\r\033[K")
                                        _sys.stdout.flush()
                                    else:
                                        console.print()
                                    spinner_active = False
                                console.print(tail, end="")
                                printed_len = len(full_response)

                # Spinner satırı hâlâ aktifse temizle
                if spinner_active:
                    if is_tty:
                        _sys.stdout.write("\r\033[K\n")
                        _sys.stdout.flush()
                    else:
                        console.print()

                if printed_len > 0 and not full_response[:printed_len].endswith("\n"):
                    console.print()

            except (OllamaConnectionError, OpenRouterConnectionError, GroqConnectionError, NineRouterConnectionError) as e:
                console.print(f"\n[bold red]Hata:[/bold red] {e}")
                break
            except (TimeoutError, OSError) as e:
                # OS seviyesinde soket timeout'u: httpx bu istisnayı her zaman
                # kendi TimeoutException'ına sarmayabiliyor (özellikle streaming
                # generator'ları içinde). Büyük modellerin CPU'da uzun prefill
                # süresi bu hataya yol açar.
                console.print(
                    f"\n[bold red]Hata:[/bold red] Ollama yanıt vermedi (zaman aşımı). "
                    f"'{self.model_name}' modeli CPU üzerinde çalışırken uzun sürebilir. "
                    f"Daha küçük bir model veya daha kısa bir prompt deneyin.\n"
                    f"[dim]Detay: {e}[/dim]"
                )
                break
            except Exception as e:
                console.print(f"\n[bold red]Hata:[/bold red] LLM ile iletişim kurulamadı: {e}")
                break
                
            self.history.add_message("assistant", full_response)
            
            # Check for tool calls (possibly multiple in one response)
            # Build the set of locally-held tool names that are NOT in the
            # global registry (e.g. delegate_task) so the parser won't reject
            # them when checking valid_tool_names.
            _local_names: set = set()
            if self.delegate_tool:
                _local_names.add(self.delegate_tool.name)
            all_tool_calls = extract_all_tool_calls(full_response, extra_valid_names=_local_names or None)
            
            if not all_tool_calls and full_response.strip() and printed_len < len(full_response):
                unprinted = full_response[printed_len:]
                if unprinted.strip():
                    console.print(unprinted)
                    printed_len = len(full_response)

            
            if not all_tool_calls and not full_response.strip():
                # Modelin ürettiği her şey (varsa) sadece <think> içindeydi,
                # görünür/final bir çıktı kalmadı. Ufak modellerde sık
                # görülür; sessizce turu bitirmek yerine kısa bir düzeltme
                # isteğiyle yeniden dene (parse_retry_limit'e kadar).
                parse_fail_count += 1
                step_count += 1
                if parse_fail_count <= self.profile.parse_retry_limit:
                    console.print(
                        "[dim]Yanıt boş geldi, modele düzeltme isteği gönderiliyor "
                        f"({parse_fail_count}/{self.profile.parse_retry_limit})...[/dim]"
                    )
                    self.history.add_message(
                        "user",
                        "Yanıtın boş geldi. Ya bir <tool_call> bloğu üret ya da kullanıcıya "
                        "kısa, normal bir cevap yaz. Başka bir şey yazma.",
                    )
                    continue
                else:
                    console.print("[bold red]Model tekrar tekrar boş yanıt üretti, döngü durduruldu.[/bold red]")
                    break

            # Detect LFM empty tool-call tags: <|tool_call_start|><|tool_call_end|>
            # These are non-empty strings but contain no real content — treat as empty.
            _stripped_resp = re.sub(r"<\|tool_call_start\|>\s*<\|tool_call_end\|>", "", full_response).strip()
            if not all_tool_calls and not _stripped_resp:
                parse_fail_count += 1
                step_count += 1
                if parse_fail_count <= self.profile.parse_retry_limit:
                    console.print(
                        "[dim]Model boş tool çağrısı üretti, düzeltme isteği gönderiliyor "
                        f"({parse_fail_count}/{self.profile.parse_retry_limit})...[/dim]"
                    )
                    self.history.add_message(
                        "user",
                        "You produced empty tool call tags with no content. "
                        "Either produce a valid <tool_call> block with a tool name and arguments, "
                        "or write a short answer to the user. Do NOT produce empty tool call tags.",
                    )
                    continue
                else:
                    console.print("[bold red]Model tekrar tekrar boş yanıt üretti, döngü durduruldu.[/bold red]")
                    break
            
            if all_tool_calls:
                if len(all_tool_calls) > 1:
                    console.print(f"\n[bold cyan]⚡ {len(all_tool_calls)} tool call algılandı, sırayla çalıştırılacak...[/bold cyan]")

                # Execute each tool call in this response sequentially
                all_results = []
                batch_aborted = False
                for tc_idx, (tool_name, args) in enumerate(all_tool_calls):
                    if len(all_tool_calls) > 1:
                        console.print(f"\n[bold cyan]  [{tc_idx+1}/{len(all_tool_calls)}] {tool_name}[/bold cyan]")
                    else:
                        console.print(f"\n[bold cyan]⚡ Tool Call Algılandı:[/bold cyan] {tool_name}")
                
                    # Format clean preview of args so huge file contents don't flood the terminal
                    args_preview = {}
                    for k, v in args.items():
                        if isinstance(v, str) and len(v) > 250:
                            args_preview[k] = v[:250] + f"... ({len(v)} karakter)"
                        elif isinstance(v, list) and len(v) > 5:
                            args_preview[k] = v[:5] + [f"... ({len(v)} öğe)"]
                        else:
                            args_preview[k] = v
                    console.print(f"[dim]Parametreler: {json.dumps(args_preview, ensure_ascii=False, indent=2)}[/dim]")
                    
                    # Repeat-detection & Cycle-detection guard
                    # Catches both consecutive duplicates (A -> A) and multi-step cycles (A -> B -> C -> A -> B -> C)
                    try:
                        call_path = args.get("path", "")
                        content_hash = hash(args.get("content", "")) if "content" in args else hash(json.dumps(args, sort_keys=True))
                        call_sig = (tool_name, call_path, content_hash)
                        call_key = (tool_name, json.dumps(args, sort_keys=True, ensure_ascii=False)[:200])
                    except Exception:
                        call_sig = (tool_name, str(args)[:200])
                        call_key = (tool_name, str(args)[:200])

                    past_occurrences = step_executed_calls.get(call_sig, 0)
                    if past_occurrences >= 1:
                        if past_occurrences == 1:
                            console.print(
                                f"[bold yellow]⚠ '{tool_name}' ({call_path or tool_name}) az önce zaten bu içerikle çalıştırıldı. Modele uyarı gönderiliyor...[/bold yellow]"
                            )
                            step_executed_calls[call_sig] = past_occurrences + 1
                            all_results.append(
                                f"UYARI: '{tool_name}' ({call_path or tool_name}) az önce zaten bu parametrelerle başarıyla çalıştırıldı ve sonucu verildi. "
                                f"Aynı aracı tekrar tekrar çağırma! İşlem bittiyse kullanıcıya tamamlandığını bildir ve başka araç çağırma."
                            )
                            continue
                        else:
                            console.print(
                                "\n[bold green]✓ Tüm işlemler tamamlandı (tekrarlayan araç çağrısı sonlandırıldı).[/bold green]\n"
                            )
                            self.history.add_message(
                                "assistant",
                                "İstenen tüm dosyalar ve işlemler başarıyla tamamlandı."
                            )
                            batch_aborted = True
                            break
                    # NOTE: step_executed_calls is set AFTER successful execution (below)
                    # Failed calls are NOT recorded so the model can retry with corrected params.

                    if call_key == self._last_call_key and self._last_call_success:
                        self._repeat_count += 1
                        if self._repeat_count < 2:
                            console.print(
                                f"[bold yellow]⚠ Aynı araç çağrısı tekrarlandı ({tool_name}). Modele uyarı gönderiliyor...[/bold yellow]"
                            )
                            all_results.append(
                                f"UYARI: '{tool_name}' aracını aynı parametrelerle az önce zaten çalıştırdın. "
                                f"Aynı aracı tekrar çağırma! Kullanıcıya işlemin tamamlandığını bildir ve bitir."
                            )
                            continue
                        else:
                            console.print("\n[bold green]✓ Tüm işlemler tamamlandı (aynı araç çağrısı tekrarlandığı için döngü sonlandırıldı).[/bold green]\n")
                            self.history.add_message("assistant", "İstenen tüm işlemler başarıyla tamamlandı.")
                            batch_aborted = True
                            break
                    else:
                        self._last_call_key = call_key
                        self._repeat_count = 0

                    
                    # Batch write pseudo-tool from the parser's code-block fallback
                    if tool_name == "_write_multiple":
                        self._handle_batch_write(args)
                        step_count += 1
                        console.print("\n[bold green]✓ Dosyalar kaydedildi.[/bold green]\n")
                        batch_aborted = True  # no need to continue, all files written
                        break
                    
                    tool = registry.get_tool(tool_name)
                    if not tool and tool_name == "delegate_task" and self.delegate_tool:
                        tool = self.delegate_tool
                        
                    if tool:
                        if tool.requires_confirm:
                            from lokal_ajan.safety.confirm import request_confirmation
                            if not request_confirmation(tool_name, args, auto_confirm=self.auto_confirm):
                                self.history.add_message("user", f"Kullanıcı {tool_name} aracının çalıştırılmasını reddetti.")
                                step_count += 1
                                continue
                        
                        if tool_name == "delegate_task":
                            # DelegateTaskTool handles its own rich output and worker agent loop
                            try:
                                result = tool.run(**args)
                            except Exception as e:
                                result = f"Error executing tool: {e}"
                        else:
                            with console.status(f"[bold yellow]⚙️ '{tool_name}' aracı çalıştırılıyor...[/bold yellow]", spinner="dots"):
                                try:
                                    # Validate arguments using Pydantic schema
                                    validated_args = tool.args_schema(**args).model_dump()
                                    
                                    # For fs tools, we might want to check path safety
                                    if "path" in validated_args:
                                        from lokal_ajan.safety.sandbox import get_safe_path
                                        try:
                                            validated_args["path"] = get_safe_path(validated_args["path"], self.workdir)
                                        except ValueError:
                                            result = (
                                                f"Error: Path '{validated_args['path']}' is outside the workspace. "
                                                f"Use RELATIVE paths like 'file.html' or './subdir/file.txt' instead of absolute paths. "
                                                f"Your workspace is '{self.workdir}', all paths must be relative to it."
                                            )
                                            result = str(result)
                                            summary = result[:300] + ("..." if len(result) > 300 else "")
                                            console.print(f"[dim]Tool Sonucu:\n{summary}[/dim]")
                                            all_results.append(f"'{tool_name}' → {result}")
                                            self._last_call_success = False
                                            step_count += 1
                                            continue
                                        
                                    result = tool.run(**validated_args)
                                except Exception as e:
                                    result = f"Error executing tool: {e}"
                            
                        result = str(result)
                        is_error = result.startswith("Error")
                        self._last_call_success = not is_error
                        result = truncate_tool_output(result, self.profile.max_tool_output)
                        summary = result[:300] + ("..." if len(result) > 300 else "")
                        console.print(f"[dim]Tool Sonucu:\n{summary}[/dim]")
                        all_results.append(f"'{tool_name}' → {result}")
                        # Only record successful calls in repeat guard — failed calls
                        # should be retryable with corrected parameters
                        if not is_error:
                            step_executed_calls[call_sig] = 1
                        step_count += 1
                    else:
                        error_msg = f"Hata: '{tool_name}' adında bir araç bulunamadı."
                        console.print(f"[bold red]{error_msg}[/bold red]")
                        all_results.append(error_msg)
                        step_count += 1

                # After executing all tool calls from this response, add combined result
                if all_results:
                    combined = "\n".join(all_results)
                    self.history.add_message(
                        "user",
                        f"Araç(lar) çalıştırıldı ve şu sonuçları döndürdü:\n"
                        f"<tool_output>\n{combined}\n</tool_output>\n"
                        f"(Şimdi yukarıdaki sonuçlara göre görevi tamamla: kalan dosyalar varsa write_file çağır veya cevabını tamamla.)"
                    )

                if batch_aborted:
                    break
                    
                # NOTE: We intentionally do NOT break after write_file/edit_file/
                # run_shell. Small models need several chained tool calls to
                # finish a multi-file project (index.html + style.css +
                # script.js). max_steps and the repeat guard prevent loops.
            else:
                # No tool call, model is done
                break
                
        if step_count >= max_steps:
            console.print("[bold red]Maksimum adım sayısına ulaşıldı, döngü durduruldu.[/bold red]")
            
        self.save_current_session()
        return True


