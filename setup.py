"""Bundle the local services so an installed CLI can bootstrap without Git."""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).parent


class BuildWithRuntime(build_py):
    def run(self):
        super().run()
        destination = Path(self.build_lib) / "agentscope_cli" / "_runtime"
        sources = [
            ROOT / "apps/api/app",
            ROOT / "apps/api/alembic",
            ROOT / "apps/web/app",
            ROOT / "apps/web/components",
            ROOT / "apps/web/lib",
            ROOT / "apps/web/public",
            ROOT / "packages/python-sdk/agentscope_sdk",
        ]
        files = [
            path for source in sources for path in source.rglob("*") if path.is_file()
        ]
        files += [
            ROOT / name
            for name in (
                "apps/api/alembic.ini",
                "apps/api/requirements.txt",
                "apps/web/package.json",
                "apps/web/package-lock.json",
                "apps/web/tsconfig.json",
                "apps/web/next-env.d.ts",
                "apps/web/next.config.ts",
                "apps/web/postcss.config.mjs",
                "apps/web/proxy.ts",
            )
        ]
        for source in files:
            if source.suffix not in {
                ".py",
                ".ini",
                ".txt",
                ".json",
                ".ts",
                ".tsx",
                ".css",
                ".mjs",
                ".svg",
                ".png",
            }:
                continue
            target = destination / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


setup(cmdclass={"build_py": BuildWithRuntime})
