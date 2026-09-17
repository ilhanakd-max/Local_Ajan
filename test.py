from lokal_ajan.agent.loop import AgentLoop
from lokal_ajan.llm.model_profiles import get_profile_for_model
from lokal_ajan.config import load_config
config = load_config()
profile = get_profile_for_model(config.default_model)
agent = AgentLoop(model_name=config.default_model, profile=profile, host=config.ollama_host, workdir=".", config=config)

tool = agent.tools_schema[4] # glob
print(tool['name'])
args = {"path": "/home/ilhan/PROJELER/test2"}
try:
    from lokal_ajan.tools.registry import registry
    t = registry.get_tool("glob")
    validated_args = t.args_schema(**args).model_dump()
    t.run(**validated_args)
    print("Success")
except Exception as e:
    print(f"Exception: {e}")
