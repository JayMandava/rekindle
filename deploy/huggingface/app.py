import gradio as gr
import spaces  # Hugging Face's default free hardware (ZeroGPU) refuses to start without one @spaces.GPU function

from rekindle.api import create_app


@spaces.GPU
def _unused_gpu_stub():  # never called: ReKindle uses no GPU
    return None


# The real app is ReKindle's FastAPI service (cockpit at "/", API under "/api"). Spaces expects a launched Gradio
# server, so launch a trivial shell (SSR off: its Node front end would intercept every path) and put ReKindle's
# routes ahead of Gradio's own.
api = create_app()
with gr.Blocks() as shell:
    gr.Markdown("ReKindle runs at the Space root.")

shell.launch(server_name="0.0.0.0", ssr_mode=False, prevent_thread_lock=True)
for route in reversed(api.router.routes):
    shell.app.router.routes.insert(0, route)
shell.block_thread()
