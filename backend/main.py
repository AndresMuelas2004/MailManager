from __future__ import annotations

import uvicorn

from api.api import app
import sys



def main() -> None:
    print(sys.path)
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
