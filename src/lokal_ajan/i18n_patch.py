from lokal_ajan.i18n import translate, load_lang

def patch_rich():
    import rich.console
    original_print = rich.console.Console.print
    def translated_print(self, *args, **kwargs):
        new_args = []
        for arg in args:
            if isinstance(arg, str):
                new_args.append(translate(arg))
            else:
                new_args.append(arg)
        return original_print(self, *new_args, **kwargs)
    rich.console.Console.print = translated_print

    import rich.prompt
    original_ask = rich.prompt.PromptBase.ask
    @classmethod
    def translated_ask(cls, prompt="", *args, **kwargs):
        if isinstance(prompt, str):
            prompt = translate(prompt)
        return original_ask.__func__(cls, prompt, *args, **kwargs)
    rich.prompt.PromptBase.ask = translated_ask
