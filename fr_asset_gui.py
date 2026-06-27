#!/usr/bin/env python3
"""Free Realms asset converter — simple desktop GUI."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import END, BooleanVar, IntVar, StringVar, Tk, filedialog, messagebox, scrolledtext, ttk

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
DEFAULT_H1Z1_SOURCE = Path(r"C:\Users\bobya\Documents\ps2ls\h1z1 assets")
DEFAULT_FR_ASSETS = Path(
    r"C:\Users\bobya\Documents\Free Realms Unpacker\editz fr assets\FR Assets 2025-07-07"
)

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _require_packages() -> None:
    missing: list[str] = []
    for package in ("numpy", "trimesh"):
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    if missing:
        message = (
            "Missing Python packages: "
            + ", ".join(missing)
            + "\n\nInstall them with:\n"
            + f'  cd "{TOOLS_DIR}"\n'
            + "  python -m pip install -r requirements.txt\n\n"
            + "Or double-click Launch Asset Converter.bat (installs automatically)."
        )
        try:
            root = Tk()
            root.withdraw()
            messagebox.showerror("Missing dependencies", message)
            root.destroy()
        except Exception:
            print(message, file=sys.stderr)
        raise SystemExit(1)


_require_packages()

from convert_to_fr import convert_assets, list_fr_actors
from generate_test_text import export_obj, make_text, prepare_for_warpstone
from port_h1z1_weapon import list_h1z1_actors, port_h1z1_actor

PRESETS: dict[str, dict] = {
    "Warpstone (test prop - worked for HELLO)": {
        "replace": "sg_warpstone_01",
        "template": TOOLS_DIR / "templates" / "sg_warpstone_01",
        "output": REPO_ROOT / "output" / "sg_warpstone_01_loose" / "custom",
        "mesh_only": False,
        "preserve_extra_meshes": True,
        "fit_template": True,
    },
    "Player body (human_m)": {
        "replace": "human_m",
        "template": TOOLS_DIR / "templates" / "human_m",
        "output": REPO_ROOT / "output" / "human_m_loose" / "custom",
        "mesh_only": True,
        "preserve_extra_meshes": True,
        "fit_template": True,
    },
    "Chatdy NPC": {
        "replace": "chatdy",
        "template": REPO_ROOT / "chatdy",
        "output": REPO_ROOT / "output" / "chatdy_loose" / "custom",
        "mesh_only": False,
        "preserve_extra_meshes": True,
        "fit_template": False,
    },
}


class AssetConverterApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Free Realms Asset Converter")
        self.root.minsize(760, 620)
        self._busy = False
        self._h1z1_actors: list[str] = []
        self._fr_actors: list[str] = []

        self.source_mode = StringVar(value="standard")
        self.input_path = StringVar()
        self.texture_path = StringVar()
        self.h1z1_source_path = StringVar(
            value=str(DEFAULT_H1Z1_SOURCE) if DEFAULT_H1Z1_SOURCE.is_dir() else ""
        )
        self.h1z1_actor = StringVar(value="Weapons_PumpShotgun01_3P")
        self.h1z1_lod = IntVar(value=0)
        self.fr_assets_path = StringVar(
            value=str(DEFAULT_FR_ASSETS) if DEFAULT_FR_ASSETS.is_dir() else ""
        )
        self.fr_actor = StringVar(value="sg_warpstone_01")
        self.client_path = StringVar(value=str(REPO_ROOT / "Client"))
        self.preset_name = StringVar(value=next(iter(PRESETS)))
        self.replace_actor = StringVar(value=PRESETS[self.preset_name.get()]["replace"])
        self.template_path = StringVar(value=str(PRESETS[self.preset_name.get()]["template"]))
        self.output_path = StringVar(value=str(PRESETS[self.preset_name.get()]["output"]))

        self.pack_z = BooleanVar(value=True)
        self.preserve_extra = BooleanVar(value=True)
        self.mesh_only = BooleanVar(value=False)
        self.fit_template = BooleanVar(value=False)

        self._build_ui()
        self._apply_preset(self.preset_name.get(), initial=True)
        self._on_source_mode_change()
        if self.fr_assets_path.get().strip():
            self._refresh_fr_actors(initial=True)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        intro = ttk.Label(
            outer,
            text=(
                "Convert OBJ/GLB models or port H1Z1 ForgeLight assets into Free Realms "
                "game files, then copy them into your client folder."
            ),
            wraplength=720,
        )
        intro.pack(anchor="w", pady=(0, 10))

        step1 = ttk.LabelFrame(outer, text="1. Source", padding=10)
        step1.pack(fill="x", pady=(0, 8))

        mode_row = ttk.Frame(step1)
        mode_row.pack(fill="x", pady=(0, 8))
        ttk.Label(mode_row, text="Source type:").pack(side="left")
        ttk.Radiobutton(
            mode_row,
            text="OBJ / GLB file",
            variable=self.source_mode,
            value="standard",
            command=self._on_source_mode_change,
        ).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(
            mode_row,
            text="H1Z1 extracted assets",
            variable=self.source_mode,
            value="h1z1",
            command=self._on_source_mode_change,
        ).pack(side="left", padx=(12, 0))

        self.standard_frame = ttk.Frame(step1)
        self.standard_frame.pack(fill="x")

        row = ttk.Frame(self.standard_frame)
        row.pack(fill="x")
        ttk.Label(row, text="Model file:").pack(side="left")
        ttk.Entry(row, textvariable=self.input_path).pack(side="left", fill="x", expand=True, padx=(8, 6))
        ttk.Button(row, text="Browse...", command=self._browse_input).pack(side="left")

        quick = ttk.Frame(self.standard_frame)
        quick.pack(fill="x", pady=(8, 0))
        ttk.Label(quick, text="Quick test:").pack(side="left")
        ttk.Button(quick, text='Make "hello" text mesh', command=self._make_hello_mesh).pack(
            side="left", padx=(8, 0)
        )

        tex_row = ttk.Frame(self.standard_frame)
        tex_row.pack(fill="x", pady=(8, 0))
        ttk.Label(tex_row, text="Texture (.dds, optional):").pack(side="left")
        ttk.Entry(tex_row, textvariable=self.texture_path, width=40).pack(
            side="left", fill="x", expand=True, padx=(8, 6)
        )
        ttk.Button(tex_row, text="Browse...", command=self._browse_texture).pack(side="left")

        self.h1z1_frame = ttk.Frame(step1)

        h1_src = ttk.Frame(self.h1z1_frame)
        h1_src.pack(fill="x")
        ttk.Label(h1_src, text="H1Z1 folder:").pack(side="left")
        ttk.Entry(h1_src, textvariable=self.h1z1_source_path).pack(
            side="left", fill="x", expand=True, padx=(8, 6)
        )
        ttk.Button(h1_src, text="Browse...", command=self._browse_h1z1_source).pack(side="left")

        h1_actor_row = ttk.Frame(self.h1z1_frame)
        h1_actor_row.pack(fill="x", pady=(8, 0))
        ttk.Label(h1_actor_row, text="H1Z1 actor:").pack(side="left")
        self.h1z1_actor_combo = ttk.Combobox(
            h1_actor_row,
            textvariable=self.h1z1_actor,
            width=44,
        )
        self.h1z1_actor_combo.pack(side="left", padx=(8, 6))
        self.h1z1_actor_combo.bind("<<ComboboxSelected>>", self._on_h1z1_actor_change)
        ttk.Button(h1_actor_row, text="Refresh list", command=self._refresh_h1z1_actors).pack(side="left")

        h1_opts = ttk.Frame(self.h1z1_frame)
        h1_opts.pack(fill="x", pady=(8, 0))
        ttk.Label(h1_opts, text="LOD:").pack(side="left")
        ttk.Spinbox(h1_opts, from_=0, to=3, width=4, textvariable=self.h1z1_lod).pack(side="left", padx=(8, 0))
        ttk.Label(
            h1_opts,
            text="Uses H1Z1 .dme mesh + diffuse texture (_C / _C_3P). XML .adr is read for file names only.",
        ).pack(side="left", padx=(12, 0))

        step2 = ttk.LabelFrame(outer, text="2. What to replace in-game", padding=10)
        step2.pack(fill="x", pady=(0, 8))

        fr_src = ttk.Frame(step2)
        fr_src.pack(fill="x")
        ttk.Label(fr_src, text="FR assets folder:").pack(side="left")
        ttk.Entry(fr_src, textvariable=self.fr_assets_path).pack(
            side="left", fill="x", expand=True, padx=(8, 6)
        )
        ttk.Button(fr_src, text="Browse...", command=self._browse_fr_assets).pack(side="left")

        fr_actor_row = ttk.Frame(step2)
        fr_actor_row.pack(fill="x", pady=(8, 0))
        ttk.Label(fr_actor_row, text="Free Realms actor:").pack(side="left")
        self.fr_actor_combo = ttk.Combobox(
            fr_actor_row,
            textvariable=self.fr_actor,
            width=44,
        )
        self.fr_actor_combo.pack(side="left", padx=(8, 6))
        self.fr_actor_combo.bind("<<ComboboxSelected>>", self._on_fr_actor_change)
        ttk.Button(fr_actor_row, text="Refresh list", command=self._refresh_fr_actors).pack(side="left")

        preset_row = ttk.Frame(step2)
        preset_row.pack(fill="x", pady=(8, 0))
        ttk.Label(preset_row, text="Options preset:").pack(side="left")
        preset_combo = ttk.Combobox(
            preset_row,
            textvariable=self.preset_name,
            values=list(PRESETS.keys()),
            state="readonly",
            width=42,
        )
        preset_combo.pack(side="left", padx=(8, 0))
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_change)

        template_row = ttk.Frame(step2)
        template_row.pack(fill="x", pady=(8, 0))
        ttk.Label(template_row, text="Template folder:").pack(side="left")
        ttk.Entry(template_row, textvariable=self.template_path).pack(
            side="left", fill="x", expand=True, padx=(8, 6)
        )
        ttk.Button(template_row, text="Browse...", command=self._browse_template).pack(side="left")

        opts = ttk.Frame(step2)
        opts.pack(fill="x", pady=(8, 0))
        self.mesh_only_check = ttk.Checkbutton(
            opts, text="Mesh only (.dme) - safest for player body", variable=self.mesh_only
        )
        self.mesh_only_check.pack(anchor="w")
        self.preserve_extra_check = ttk.Checkbutton(
            opts,
            text="Keep extra template geometry (needed for warpstone visibility)",
            variable=self.preserve_extra,
        )
        self.preserve_extra_check.pack(anchor="w")
        self.fit_template_check = ttk.Checkbutton(
            opts, text="Fit model to template size", variable=self.fit_template
        )
        self.fit_template_check.pack(anchor="w")
        ttk.Checkbutton(opts, text="Also write compressed .z files", variable=self.pack_z).pack(anchor="w")

        step3 = ttk.LabelFrame(outer, text="3. Build and install", padding=10)
        step3.pack(fill="x", pady=(0, 8))

        out_row = ttk.Frame(step3)
        out_row.pack(fill="x")
        ttk.Label(out_row, text="Output folder:").pack(side="left")
        ttk.Entry(out_row, textvariable=self.output_path).pack(side="left", fill="x", expand=True, padx=(8, 6))
        ttk.Button(out_row, text="Browse...", command=self._browse_output).pack(side="left")

        client_row = ttk.Frame(step3)
        client_row.pack(fill="x", pady=(8, 0))
        ttk.Label(client_row, text="Game client folder:").pack(side="left")
        ttk.Entry(client_row, textvariable=self.client_path).pack(
            side="left", fill="x", expand=True, padx=(8, 6)
        )
        ttk.Button(client_row, text="Browse...", command=self._browse_client).pack(side="left")

        actions = ttk.Frame(step3)
        actions.pack(fill="x", pady=(10, 0))
        self.convert_btn = ttk.Button(actions, text="Convert", command=self._start_convert)
        self.convert_btn.pack(side="left")
        self.install_btn = ttk.Button(actions, text="Copy into game folder", command=self._install_to_client)
        self.install_btn.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open output folder", command=self._open_output).pack(side="left", padx=(8, 0))

        self.status = StringVar(value="Ready.")
        ttk.Label(outer, textvariable=self.status).pack(anchor="w", pady=(4, 4))

        log_frame = ttk.LabelFrame(outer, text="Log", padding=6)
        log_frame.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(log_frame, height=10, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert(END, message + "\n")
        self.log.see(END)
        self.log.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.convert_btn.configure(state=state)
        self.install_btn.configure(state=state)

    def _sync_replace_actor_from_fr(self) -> None:
        actor = self.fr_actor.get().strip()
        if actor:
            self.replace_actor.set(actor)

    def _fr_assets_dir(self) -> Path:
        return Path(self.fr_assets_path.get().strip())

    def _output_dir_for_job(self) -> Path:
        replace = self.fr_actor.get().strip() or self.replace_actor.get().strip() or "asset"
        if self.source_mode.get() == "h1z1":
            sub = self.h1z1_actor.get().strip().lower() or "h1z1_asset"
        else:
            sub = "custom"
        return REPO_ROOT / "output" / f"{replace}_loose" / sub

    def _update_output_path(self) -> None:
        self.output_path.set(str(self._output_dir_for_job()))

    def _on_source_mode_change(self) -> None:
        is_h1z1 = self.source_mode.get() == "h1z1"
        if is_h1z1:
            self.standard_frame.pack_forget()
            self.h1z1_frame.pack(fill="x")
            self.mesh_only_check.state(["disabled"])
            if not self._h1z1_actors:
                self._refresh_h1z1_actors()
            self._update_output_path()
        else:
            self.h1z1_frame.pack_forget()
            self.standard_frame.pack(fill="x")
            self.mesh_only_check.state(["!disabled"])
            self._update_output_path()

    def _on_fr_actor_change(self, _event=None) -> None:
        self._sync_replace_actor_from_fr()
        assets_dir = self._fr_assets_dir()
        if assets_dir.is_dir():
            self.template_path.set(str(assets_dir))
        self._update_output_path()

    def _on_h1z1_actor_change(self, _event=None) -> None:
        self._update_output_path()

    def _apply_preset(self, name: str, initial: bool = False) -> None:
        preset = PRESETS.get(name)
        if not preset:
            return
        if preset["replace"] in self._fr_actors or not self._fr_actors:
            self.fr_actor.set(preset["replace"])
        self._sync_replace_actor_from_fr()
        assets_dir = self._fr_assets_dir()
        if assets_dir.is_dir():
            self.template_path.set(str(assets_dir))
        else:
            self.template_path.set(str(preset["template"]))
        self._update_output_path()
        self.mesh_only.set(preset["mesh_only"])
        self.preserve_extra.set(preset["preserve_extra_meshes"])
        self.fit_template.set(preset["fit_template"])
        if not initial:
            self._log(f"Preset loaded: {name}")

    def _on_preset_change(self, _event=None) -> None:
        self._apply_preset(self.preset_name.get())

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose 3D model",
            filetypes=[
                ("3D models", "*.obj *.glb *.gltf"),
                ("Wavefront OBJ", "*.obj"),
                ("glTF", "*.glb *.gltf"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.input_path.set(path)

    def _browse_texture(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose texture",
            filetypes=[("DDS texture", "*.dds"), ("All files", "*.*")],
        )
        if path:
            self.texture_path.set(path)

    def _browse_h1z1_source(self) -> None:
        path = filedialog.askdirectory(title="Choose H1Z1 extracted assets folder")
        if path:
            self.h1z1_source_path.set(path)
            self._refresh_h1z1_actors()

    def _browse_fr_assets(self) -> None:
        path = filedialog.askdirectory(title="Choose Free Realms unpacked assets folder")
        if path:
            self.fr_assets_path.set(path)
            self._refresh_fr_actors()

    def _browse_template(self) -> None:
        path = filedialog.askdirectory(title="Choose template actor folder")
        if path:
            self.template_path.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.output_path.set(path)

    def _browse_client(self) -> None:
        path = filedialog.askdirectory(title="Choose Free Realms client folder")
        if path:
            self.client_path.set(path)

    def _refresh_h1z1_actors(self) -> None:
        if self._busy:
            return
        source = Path(self.h1z1_source_path.get().strip())

        def worker() -> None:
            try:
                self.root.after(0, lambda: self._set_busy(True))
                self.root.after(0, lambda: self.status.set("Scanning H1Z1 actors..."))
                actors = list_h1z1_actors(source)

                def done() -> None:
                    self._h1z1_actors = actors
                    self.h1z1_actor_combo["values"] = actors
                    current = self.h1z1_actor.get().strip()
                    if current not in actors and actors:
                        if "Weapons_PumpShotgun01_3P" in actors:
                            self.h1z1_actor.set("Weapons_PumpShotgun01_3P")
                        else:
                            self.h1z1_actor.set(actors[0])
                    self._update_output_path()
                    self._log(f"Found {len(actors)} H1Z1 actors in {source}")
                    self.status.set(f"Found {len(actors)} H1Z1 actors.")

                self.root.after(0, done)
            except Exception as exc:
                error_message = str(exc)

                def fail(msg: str = error_message) -> None:
                    messagebox.showerror("H1Z1 scan failed", msg)
                    self._log(f"ERROR: {msg}")
                    self.status.set("H1Z1 scan failed.")

                self.root.after(0, fail)
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_fr_actors(self, initial: bool = False) -> None:
        if self._busy:
            return
        source = self._fr_assets_dir()

        def worker() -> None:
            try:
                self.root.after(0, lambda: self._set_busy(True))
                self.root.after(0, lambda: self.status.set("Scanning Free Realms actors..."))
                actors = list_fr_actors(source)

                def done() -> None:
                    self._fr_actors = actors
                    self.fr_actor_combo["values"] = actors
                    current = self.fr_actor.get().strip()
                    if current not in actors and actors:
                        if "sg_warpstone_01" in actors:
                            self.fr_actor.set("sg_warpstone_01")
                        else:
                            self.fr_actor.set(actors[0])
                    self._on_fr_actor_change()
                    if not initial:
                        self._log(f"Found {len(actors)} Free Realms actors in {source}")
                    self.status.set(f"Found {len(actors)} Free Realms actors.")

                self.root.after(0, done)
            except Exception as exc:
                error_message = str(exc)

                def fail(msg: str = error_message) -> None:
                    if not initial:
                        messagebox.showerror("FR asset scan failed", msg)
                    self._log(f"ERROR: {msg}")
                    self.status.set("FR asset scan failed.")

                self.root.after(0, fail)
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _make_hello_mesh(self) -> None:
        if self._busy:
            return
        try:
            self._set_busy(True)
            self.status.set('Building "hello" test mesh...')
            mesh = make_text("hello")
            if self.preset_name.get().startswith("Warpstone"):
                mesh = prepare_for_warpstone(mesh)
            out = REPO_ROOT / "output" / "hello_test" / "source" / "hello.obj"
            export_obj(mesh, out)
            self.source_mode.set("standard")
            self._on_source_mode_change()
            self.input_path.set(str(out))
            self._log(f"Created test mesh: {out}")
            self.status.set('Test mesh ready - click Convert.')
        except Exception as exc:
            messagebox.showerror("Could not build test mesh", str(exc))
            self._log(f"ERROR: {exc}")
        finally:
            self._set_busy(False)

    def _build_standard_args(self) -> argparse.Namespace:
        input_file = Path(self.input_path.get().strip())
        if not input_file.is_file():
            raise FileNotFoundError(f"Model file not found:\n{input_file}")

        template = Path(self.template_path.get().strip())
        if not template.is_dir():
            raise FileNotFoundError(f"Template folder not found:\n{template}")

        output = Path(self.output_path.get().strip())
        texture = Path(self.texture_path.get().strip()) if self.texture_path.get().strip() else None
        if texture and not texture.is_file():
            raise FileNotFoundError(f"Texture file not found:\n{texture}")

        return argparse.Namespace(
            input=input_file,
            replace=self.fr_actor.get().strip() or self.replace_actor.get().strip(),
            no_replace=False,
            name=None,
            template=template,
            output=output,
            scale=None,
            skeleton="treeble",
            copy_animations=None,
            texture=texture,
            pack=self.pack_z.get(),
            write_adr=None,
            mesh_scale=1.0,
            mesh_offset=(0.0, 0.0, 0.0),
            preserve_extra_meshes=self.preserve_extra.get(),
            fit_template=self.fit_template.get(),
            mesh_only=self.mesh_only.get(),
        )

    def _build_h1z1_args(self) -> argparse.Namespace:
        source = Path(self.h1z1_source_path.get().strip())
        if not source.is_dir():
            raise FileNotFoundError(f"H1Z1 folder not found:\n{source}")

        actor = self.h1z1_actor.get().strip()
        if not actor:
            raise ValueError("Enter or select an H1Z1 actor name.")

        template = Path(self.template_path.get().strip())
        if not template.is_dir():
            raise FileNotFoundError(f"Template folder not found:\n{template}")

        return argparse.Namespace(
            source=source,
            actor=actor,
            replace=self.fr_actor.get().strip() or self.replace_actor.get().strip(),
            template=template,
            output=Path(self.output_path.get().strip()),
            lod=int(self.h1z1_lod.get()),
            no_fit_template=not self.fit_template.get(),
            no_preserve_extra_meshes=not self.preserve_extra.get(),
            pack=self.pack_z.get(),
            export_preview=False,
        )

    def _start_convert(self) -> None:
        if self._busy:
            return
        is_h1z1 = self.source_mode.get() == "h1z1"
        try:
            job_args = self._build_h1z1_args() if is_h1z1 else self._build_standard_args()
        except Exception as exc:
            messagebox.showerror("Conversion failed", str(exc))
            self._log(f"ERROR: {exc}")
            return

        def worker() -> None:
            try:
                self.root.after(0, lambda: self._set_busy(True))
                label = "Porting H1Z1 asset..." if is_h1z1 else "Converting..."
                self.root.after(0, lambda: self.status.set(label))

                manifest = port_h1z1_actor(job_args) if is_h1z1 else convert_assets(job_args)

                output_dir = manifest["output_dir"]

                def done() -> None:
                    if is_h1z1:
                        self._log(
                            f"H1Z1 port done - {manifest.get('h1z1_actor', '?')} -> "
                            f"{manifest.get('actor', '?')}"
                        )
                        self._log(
                            f"  Mesh: {manifest.get('imported_vertices', '?')} verts, "
                            f"{manifest.get('imported_triangles', '?')} tris"
                        )
                        if manifest.get("h1z1_diffuse"):
                            self._log(f"  Diffuse: {manifest['h1z1_diffuse']}")
                        if manifest.get("h1z1_dma_textures"):
                            slots = ", ".join(manifest["h1z1_dma_textures"])
                            self._log(f"  Material slots: {slots}")
                        if manifest.get("copied_h1z1_textures"):
                            self._log(
                                f"  Textures copied: {len(manifest['copied_h1z1_textures'])} file(s)"
                            )
                        if manifest.get("h1z1_texture_resolved") is False:
                            self._log(
                                "  WARNING: No H1Z1 color map found - result may look untextured."
                            )
                    else:
                        self._log(f"Done - wrote {len(manifest['files_written'])} files to {output_dir}")
                    for note in manifest.get("notes", []):
                        self._log(f"  - {note}")
                    self.status.set("Conversion finished. Copy into game folder or restart if already installed.")
                    messagebox.showinfo(
                        "Conversion complete",
                        f"Game files saved to:\n{output_dir}\n\n"
                        "Click Copy into game folder to install, then check in-game.",
                    )

                self.root.after(0, done)
            except Exception as exc:
                error_message = str(exc)

                def fail(msg: str = error_message) -> None:
                    self._log(f"ERROR: {msg}")
                    messagebox.showerror("Conversion failed", msg)
                    self.status.set("Conversion failed.")

                self.root.after(0, fail)
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _game_files_in_output(self) -> list[Path]:
        output = Path(self.output_path.get().strip())
        if not output.is_dir():
            raise FileNotFoundError(f"Output folder not found:\n{output}\n\nRun Convert first.")
        skip_names = {"install.json", "README.txt"}
        files = [
            path
            for path in output.iterdir()
            if path.is_file() and path.name not in skip_names and path.suffix != ".z"
        ]
        if not files:
            raise FileNotFoundError(f"No game files in:\n{output}\n\nRun Convert first.")
        return files

    def _install_to_client(self) -> None:
        if self._busy:
            return
        try:
            client = Path(self.client_path.get().strip())
            if not client.is_dir():
                raise FileNotFoundError(f"Client folder not found:\n{client}")

            files = self._game_files_in_output()
            if not messagebox.askyesno(
                "Install to game folder?",
                f"Copy {len(files)} file(s) into:\n{client}\n\n"
                "Existing files with the same name will be overwritten.",
            ):
                return

            self._set_busy(True)
            self.status.set("Copying into client folder...")
            copied = 0
            for source in files:
                target = client / source.name
                shutil.copy2(source, target)
                self._log(f"Installed {source.name}")
                copied += 1

            self.status.set(f"Installed {copied} file(s). Launch the game to test.")
            messagebox.showinfo(
                "Installed",
                f"Copied {copied} file(s) to:\n{client}\n\n"
                "If you still see the old model, delete any matching .z cache file "
                "in the client folder and try again.",
            )
        except Exception as exc:
            messagebox.showerror("Install failed", str(exc))
            self._log(f"ERROR: {exc}")
            self.status.set("Install failed.")
        finally:
            self._set_busy(False)

    def _open_output(self) -> None:
        path = Path(self.output_path.get().strip())
        if not path.is_dir():
            messagebox.showwarning("No output folder", "Output folder does not exist yet. Run Convert first.")
            return
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        else:
            webbrowser.open(path.as_uri())


def main() -> None:
    root = Tk()
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    AssetConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
