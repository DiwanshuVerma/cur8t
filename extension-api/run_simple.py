#!/usr/bin/env python3
"""
Simple runner for the VS Code extension API
This version bypasses database dependencies for development
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main_simple:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
        workers=1,
        loop="asyncio",
        http="httptools",
    )
