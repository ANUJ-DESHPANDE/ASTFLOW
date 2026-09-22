"""Container-only entry point. Publish the container port on host loopback."""
import uvicorn
from backend.app.config import ROOT
from backend.app.main import create_app
from scripts.setup_demo import setup

if __name__ == '__main__':
    setup()
    app = create_app()
    for version in ('v1', 'v2', 'working-tree'):
        app.state.service.index(str(ROOT/'examples/demo-repo'), version)
    uvicorn.run(app, host='0.0.0.0', port=8000)
