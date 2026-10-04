import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

_HOME = tempfile.mkdtemp()
os.environ["DLSS5_DASHBOARD_HOME"] = _HOME

from dlss5_dashboard import (backup, compare_key, games, pe, server, settings_schema, store,  # noqa: E402
                            sysinfo, verify, xbox)
from dlss5_dashboard.inifile import IniDoc  # noqa: E402

OPTI_SAMPLE = """; header comment
[DLSS]
; Enables calls to original NVNGX
Enabled=auto
RenderPresetOverride=auto

[DlssNr]
; neural rendering
Enabled=auto
TransferStrength=auto
"""


class IniTests(unittest.TestCase):
    def test_set_keeps_comments_and_adds_keys(self):
        doc = IniDoc(OPTI_SAMPLE)
        doc.set("DLSS", "RenderPresetOverride", True)
        doc.set("DlssNr", "Preset", 2)
        doc.set("MfgUnlock", "Enabled", "true")
        text = doc.text()
        self.assertIn("; Enables calls to original NVNGX", text)
        self.assertIn("RenderPresetOverride=true", text)
        self.assertEqual(doc.get("dlssnr", "preset"), "2")
        self.assertTrue(text.rstrip().endswith("[MfgUnlock]\nEnabled=true"))
        # key added inside its own section, not at the end of the file
        self.assertLess(text.index("Preset=2"), text.index("[MfgUnlock]"))

    def test_sectionless_file(self):
        doc = IniDoc("enabled=1\nmode=2\n")
        doc.set(None, "work_resolution", 75)
        self.assertEqual(doc.get(None, "work_resolution"), "75")
        self.assertEqual(doc.get(None, "mode"), "2")


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_feeder_roundtrip_and_validation(self):
        (self.dir / "dlss5-feed.cfg").write_text("enabled=1\nmode=2\npreset=0\n")
        vals = settings_schema.read_values(settings_schema.FEEDER, self.dir)
        self.assertEqual(vals[".preset"], "0")
        self.assertEqual(vals[".work_resolution"], "100")  # default when key absent
        changed = settings_schema.write_values(settings_schema.FEEDER, self.dir,
                                               {".preset": "11", ".work_resolution": "75"})
        self.assertEqual(sorted(changed), [".preset", ".work_resolution"])
        cfg = (self.dir / "dlss5-feed.cfg").read_text()
        self.assertIn("preset=11", cfg)
        self.assertIn("work_resolution=75", cfg)
        with self.assertRaises(ValueError):
            settings_schema.write_values(settings_schema.FEEDER, self.dir, {".work_resolution": "20"})
        with self.assertRaises(ValueError):
            settings_schema.write_values(settings_schema.FEEDER, self.dir, {".preset": "99"})
        with self.assertRaises(ValueError):
            settings_schema.write_values(settings_schema.FEEDER, self.dir, {".bogus": "1"})

    def test_optiscaler_auto_and_numbers(self):
        (self.dir / "OptiScaler.ini").write_text(OPTI_SAMPLE)
        settings_schema.write_values(settings_schema.OPTISCALER, self.dir, {
            "DlssNr.Enabled": "true", "DlssNr.TransferStrength": "1.25",
            "DlssNr.Preset": "auto", "DLSS.RenderPresetForAll": "11"})
        doc = IniDoc.load(self.dir / "OptiScaler.ini")
        self.assertEqual(doc.get("DlssNr", "Enabled"), "true")
        self.assertEqual(doc.get("DlssNr", "TransferStrength"), "1.25")
        self.assertEqual(doc.get("DLSS", "RenderPresetForAll"), "11")
        self.assertIsNone(settings_schema.read_values(settings_schema.FEEDER, self.dir))


class PeTests(unittest.TestCase):
    def test_reads_a_real_windows_exe(self):
        candidates = list(Path.home().glob(".local/share/uv/tools/*/lib/python3*/site-packages/distlib/t64.exe"))
        if not candidates:
            self.skipTest("no Windows PE available")
        info = pe.read_pe(candidates[0])
        self.assertEqual(info["machine"], "x64")
        self.assertIn("kernel32.dll", info["imports"])

    def test_garbage(self):
        p = Path(tempfile.mkdtemp()) / "x.exe"
        p.write_bytes(b"MZ" + b"\0" * 100)
        self.assertEqual(pe.read_pe(p)["machine"], None)
        self.assertEqual(pe.guess_api(["kernel32.dll", "d3d11.dll"]), "D3D11")


class SteamTests(unittest.TestCase):
    def test_library_and_ets2(self):
        root = Path(tempfile.mkdtemp())
        lib2 = Path(tempfile.mkdtemp())
        (root / "steamapps").mkdir()
        (root / "steamapps/libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n "0"\n {\n  "path" "%s"\n }\n "1"\n {\n  "path" "%s"\n }\n}\n'
            % (str(root).replace("\\", "\\\\"), str(lib2).replace("\\", "\\\\")))
        (lib2 / "steamapps/common/Euro Truck Simulator 2/bin/win_x64").mkdir(parents=True)
        exe = lib2 / "steamapps/common/Euro Truck Simulator 2/bin/win_x64/eurotrucks2.exe"
        exe.write_bytes(b"MZ")
        (lib2 / "steamapps/appmanifest_227300.acf").write_text(
            '"AppState"\n{\n "appid" "227300"\n "name" "Euro Truck Simulator 2"\n'
            ' "installdir" "Euro Truck Simulator 2"\n}\n')
        (lib2 / "steamapps/appmanifest_228980.acf").write_text(
            '"AppState"\n{\n "appid" "228980"\n "name" "Steamworks Common Redistributables"\n'
            ' "installdir" "Steamworks Shared"\n}\n')
        found = games.steam_games(root)
        self.assertEqual([g["id"] for g in found], ["steam:227300"])
        a = games.analyze(found[0])
        self.assertEqual(Path(a["exe"]), exe)
        self.assertEqual(a["api"], "D3D11")
        self.assertEqual(a["recommended_route"], "feeder")
        self.assertFalse(a["anticheat"])

    def test_native_dlss_and_anticheat_detected(self):
        d = Path(tempfile.mkdtemp())
        (d / "Game.exe").write_bytes(b"MZ" + b"\0" * 2000)
        (d / "nvngx_dlss.dll").write_bytes(b"x")
        (d / "EasyAntiCheat").mkdir()
        a = games.analyze({"id": "manual:x", "name": "G", "install_dir": str(d)})
        self.assertEqual(a["recommended_route"], "optiscaler")
        self.assertIn("Easy Anti-Cheat", a["anticheat"])
        self.assertTrue(a["warnings"])

    def test_dlls_we_installed_are_not_native_dlss(self):
        d = Path(tempfile.mkdtemp())
        (d / "game.exe").write_bytes(b"MZ")
        m = backup.begin("manual:ours", str(d), "feeder")
        (d / "nvngx_dlss.dll").write_bytes(b"x")  # the feeder ships this
        backup.finish(m)
        store.update(lambda s: s["manifests"].__setitem__("manual:ours", m))
        a = games.analyze({"id": "manual:ours", "name": "G", "install_dir": str(d)})
        self.assertEqual(a["native_dlss"], {})
        self.assertEqual(a["recommended_route"], "feeder")
        store.update(lambda s: s["manifests"].pop("manual:ours"))


class BackupTests(unittest.TestCase):
    def test_install_toggle_restore_roundtrip(self):
        d = Path(tempfile.mkdtemp())
        (d / "game.exe").write_bytes(b"MZ")
        (d / "settings.ini").write_text("original")
        m = backup.begin("manual:t", str(d), "feeder")
        # what an installer does
        (d / "dxgi.dll").write_bytes(b"reshade")
        (d / "ReShade.ini").write_text("x")
        (d / "reshade-shaders/Shaders").mkdir(parents=True)
        (d / "reshade-shaders/Shaders/a.fx").write_text("x")
        (d / "settings.ini").write_text("changed by installer!")
        backup.finish(m)
        self.assertIn("dxgi.dll", m["added"])
        self.assertEqual(m["changed"], ["settings.ini"])
        self.assertEqual(backup.proxies(m), ["dxgi.dll"])

        backup.set_enabled(m, False)
        self.assertFalse((d / "dxgi.dll").exists())
        self.assertTrue((d / "dxgi.dll.dlss5off").exists())
        self.assertFalse(backup.is_enabled(m))
        backup.set_enabled(m, True)
        self.assertTrue(backup.is_enabled(m))

        backup.set_enabled(m, False)  # restore must also handle the disabled state
        backup.restore(m)
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["game.exe", "settings.ini"])
        self.assertEqual((d / "settings.ini").read_text(), "original")


class SysinfoTests(unittest.TestCase):
    def test_rtx4070(self):
        gpus = sysinfo.parse_nvidia_smi("NVIDIA GeForce RTX 4070, 581.57, 12282, 8.9\n")
        self.assertEqual(gpus[0]["series"], "RTX 40")
        self.assertEqual(sysinfo.assess(gpus[0])["level"], "community")
        self.assertEqual(sysinfo.assess(None)["level"], "none")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def req(self, method, path, body=None, token=True, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            h["X-Token"] = server.TOKEN
        if body is not None:
            h["Content-Type"] = "application/json"
        c.request(method, path, json.dumps(body) if body is not None else None, h)
        r = c.getresponse()
        return r.status, r.read()

    def test_page_has_token(self):
        status, body = self.req("GET", "/", token=False)
        self.assertEqual(status, 200)
        self.assertIn(server.TOKEN.encode(), body)

    def test_api_needs_token_and_local_host(self):
        self.assertEqual(self.req("GET", "/api/games", token=False)[0], 403)
        self.assertEqual(self.req("GET", "/api/games", host="evil.example:80")[0], 403)
        self.assertEqual(self.req("GET", "/api/games")[0], 200)

    def test_manual_game_flow(self):
        d = Path(tempfile.mkdtemp())
        exe = d / "Game.exe"
        exe.write_bytes(b"MZ")
        status, body = self.req("POST", "/api/games/add", {"exe": str(exe)})
        self.assertEqual(status, 200, body)
        gid = json.loads(body)["id"]
        status, body = self.req("GET", f"/api/game?id={gid}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["recommended_route"], "feeder")
        status, body = self.req("POST", "/api/settings", {"id": gid, "file": "feeder", "values": {}})
        self.assertEqual(status, 400)  # no dlss5-feed.cfg yet
        self.assertEqual(self.req("POST", "/api/games/add", {"exe": str(d / "nope.exe")})[0], 400)
        self.assertEqual(self.req("GET", "/../server.py")[0], 404)
        store.update(lambda s: s["manual_games"].clear())


if __name__ == "__main__":
    unittest.main()


class VerifyTests(unittest.TestCase):
    LOG = (
        "15:53:40:822 [1] | INFO  | [DLSS 5 Neural Rendering] DLSS5 Generic: frame contract path=inline "
        "in=2560x1440 out=2560x1440 hdr=1\n"
        "15:53:49:220 [1] | INFO  | [DLSS 5 Neural Rendering] DLSS5 Generic: telemetry t=4291.87s "
        "win=30.00s presents=1799 ticks=1799 fps=59.96 frame_ms[avg=16.68]\n"
        "15:53:49:222 [1] | INFO  | [DLSS 5 Neural Rendering] DLSS5 Generic: NR cost: gpu_ms=11.55 "
        "frame_ms=16.67 share=0.693 present_ms=11.55 | NR: 11.5 ms of GPU time per frame "
        "(estimate: 195 fps without NR, 60 fps with it)\n"
        "15:54:12:148 [1] | INFO  | [DLSS 5 Neural Rendering] DLSS5 Generic: NR-VERDICT v3 state=ENGAGED "
        "stage=- reason=warmup missing=heaps seen=364596 eligible=182323 evals=182309 ratio=0.9999 "
        "unaccounted=0\n"
        "15:54:12:148 [1] | INFO  | [DLSS 5 Neural Rendering] DLSS5 Generic: NR-WARN summary active=0 slugs=-\n"
    )

    def test_engaged(self):
        d = Path(tempfile.mkdtemp())
        (d / "ReShade.log").write_text(self.LOG)
        v = verify.check(d)
        self.assertEqual(v["level"], "ok")
        facts = dict(v["facts"])
        self.assertEqual(facts["Stato modello neurale"], "ENGAGED")
        self.assertEqual(facts["Risoluzione elaborata"], "2560x1440")
        self.assertEqual(facts["FPS stimati"], "60 con DLSS 5 / 195 senza")
        self.assertEqual(facts["FPS misurati"], "60")

    def test_refused_and_missing(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(verify.check(d)["level"], "error")
        (d / "ReShade.log").write_text("x | ERROR | feature 18 create failed with 0xbad00001\n")
        self.assertIn("rifiuta", verify.check(d)["title"])


class CompareKeyTests(unittest.TestCase):
    def test_sets_key_on_feeder_techniques(self):
        d = Path(tempfile.mkdtemp())
        (d / "ReShade.ini").write_text("[GENERAL]\nPresetPath=.\\ReShadePreset.ini\n")
        (d / "ReShadePreset.ini").write_text(
            "PreprocessorDefinitions=\nTechniques=Lumenite_Kernel@lumenite_Kernel.fx,DLSS5_Feed@DLSS5_Feed.fx\n"
            "TechniqueSorting=Lumenite_Kernel@lumenite_Kernel.fx,DLSS5_Feed@DLSS5_Feed.fx\n\n"
            "[DLSS5_Feed.fx]\nDLSS5_MV_PROVIDER=3\n")
        r = compare_key.read(d)
        self.assertEqual(r["value"], "0,0,0,0")
        compare_key.write(d, "145,0,0,0")
        text = (d / "ReShadePreset.ini").read_text()
        self.assertIn("KeyDLSS5_Feed@DLSS5_Feed.fx=145,0,0,0", text)
        self.assertIn("KeyLumenite_Kernel@lumenite_Kernel.fx=145,0,0,0", text)
        self.assertLess(text.index("KeyDLSS5_Feed"), text.index("[DLSS5_Feed.fx]"))
        self.assertEqual(compare_key.read(d)["value"], "145,0,0,0")
        with self.assertRaises(ValueError):
            compare_key.write(d, "999,0,0,0")


class XboxTests(unittest.TestCase):
    CONFIG = """<?xml version="1.0" encoding="utf-8"?>
<Game configVersion="1">
  <Identity Name="Publisher.CoolGame" Publisher="CN=X" Version="1.0.0.0"/>
  <ExecutableList>
    <Executable Name="gamelaunchhelper.exe" Id="Game" TargetDeviceFamily="PC"/>
  </ExecutableList>
  <ShellVisuals DefaultDisplayName="Cool Game"/>
</Game>"""

    def test_gaming_root_and_scan(self):
        drive = Path(tempfile.mkdtemp())
        path = "\\Giochi Xbox"
        (drive / ".GamingRoot").write_bytes(b"RGBX" + (1).to_bytes(4, "little")
                                            + (path + "\0").encode("utf-16-le"))
        self.assertEqual(xbox.parse_gaming_root((drive / ".GamingRoot").read_bytes()), [path])
        content = drive / "Giochi Xbox" / "Cool Game" / "Content"
        (content / "Binaries").mkdir(parents=True)
        (content / "MicrosoftGame.config").write_text(self.CONFIG)
        (content / "gamelaunchhelper.exe").write_bytes(b"MZ" + b"\0" * 10)
        (content / "Binaries" / "CoolGame.exe").write_bytes(b"MZ" + b"\0" * 5000)
        (drive / "XboxGames").mkdir()  # default folder, empty

        found = xbox.xbox_games([str(drive)])
        self.assertEqual(len(found), 1)
        g = found[0]
        self.assertEqual(g["id"], "xbox:Publisher.CoolGame")
        self.assertEqual(g["name"], "Cool Game")
        self.assertEqual(Path(g["exe"]).name, "CoolGame.exe")  # not the launcher wrapper
        self.assertEqual(g["xbox"]["app_id"], "Game")
        a = games.analyze(g)
        self.assertEqual(a["recommended_route"], "feeder")
        self.assertTrue(any("Xbox" in n for n in a["notes"]))

    def test_bad_config_is_skipped(self):
        d = Path(tempfile.mkdtemp())
        (d / "Broken" / "Content").mkdir(parents=True)
        (d / "Broken" / "Content" / "MicrosoftGame.config").write_text("<not xml")
        self.assertEqual(xbox.scan(d), [])


class OptiVerifyAndDlcTests(unittest.TestCase):
    def test_optiscaler_log(self):
        d = Path(tempfile.mkdtemp())
        v = verify.check(d, "optiscaler")
        self.assertEqual(v["title"], "Nessun OptiScaler.log")
        (d / "OptiScaler.log").write_text(
            "[12:00:00] [info] DLSS-NR (proxy): feature created at 2560x1440 through the driver's nvngx\n"
            "[12:01:00] [info] Neural Rendering key pressed, will be toggling the pass\n")
        v = verify.check(d, "optiscaler")
        self.assertEqual(v["level"], "ok")
        (d / "OptiScaler.log").write_text(
            "[12:00:00] [error] DLSS-NR (proxy): CreateFeature(18) failed 0xBAD00001 -- falling back\n")
        self.assertIn("non partito", verify.check(d, "optiscaler")["title"])

    def test_dlc_packages_are_not_games(self):
        d = Path(tempfile.mkdtemp())
        c = d / "Some DLC" / "Content"
        c.mkdir(parents=True)
        (c / "MicrosoftGame.config").write_text(
            '<Game configVersion="1"><Identity Name="Pub.DLC1" Publisher="CN=X" Version="1.0.0.0"/>'
            '<ShellVisuals DefaultDisplayName="DLC 1"/></Game>')
        self.assertEqual(xbox.scan(d), [])


class NeuralSwitchTests(unittest.TestCase):
    def test_launch_writes_dlssnr_enabled(self):
        from dlss5_dashboard import launcher
        d = Path(tempfile.mkdtemp())
        (d / "Game.exe").write_bytes(b"MZ")
        (d / "OptiScaler.ini").write_text("[DlssNr]\nEnabled=auto\n")
        m = backup.begin("manual:nr", str(d), "optiscaler")
        backup.finish(m)
        store.update(lambda s: s["manifests"].__setitem__("manual:nr", m))
        opened = []
        orig = launcher._open
        launcher._open = opened.append
        try:
            game = {"id": "manual:nr", "source": "xbox", "xbox": {"identity": "X"}, "exe": str(d / "Game.exe")}
            from dlss5_dashboard import xbox
            orig_t, xbox.launch_target = xbox.launch_target, lambda g: "shell:AppsFolder\\X_1!Game"
            try:
                launcher.launch(game, True, "", neural_on=False)
            finally:
                xbox.launch_target = orig_t
        finally:
            launcher._open = orig
            store.update(lambda s: s["manifests"].pop("manual:nr"))
        self.assertEqual(IniDoc.load(d / "OptiScaler.ini").get("DlssNr", "Enabled"), "false")
        self.assertEqual(opened, ["shell:AppsFolder\\X_1!Game"])
