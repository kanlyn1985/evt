; =========================
; obc_export_win.il (Windows-safe)
; =========================

(procedure (obcWriteTextFile (path lines))
  (let ((fp))
    (setq fp (outfile path))
    (foreach line lines
      (fprintf fp "%s\n" line)
    )
    (close fp)
  )
)

(procedure (obcNowStamp)
  (let ((tstr))
    (setq tstr (getCurrentTime))
    ; e.g. 2026-02-25_10-30-15
    (buildString(
      substring(tstr 21 24) "-"
      substring(tstr 5 7) "-"
      substring(tstr 9 10) "_"
      substring(tstr 12 13) "-"
      substring(tstr 15 16) "-"
      substring(tstr 18 19)
    ))
  )
)

(procedure (obcMkdirWin (dir))
  ; Windows cmd mkdir: create only when missing
  (axlShell(sprintf(nil "cmd /c if not exist \"%s\" mkdir \"%s\"" dir dir)))
)

(procedure (obcExportWin (boardPath outRoot))
  (let ((stamp outDir logPath cmdPath metaPath cmdLines))
    (setq stamp   (obcNowStamp))
    (setq outDir  (sprintf nil "%s\\%s" outRoot stamp))
    (setq logPath (sprintf nil "%s\\run.log" outDir))
    (setq cmdPath (sprintf nil "%s\\export.scr" outDir))
    (setq metaPath (sprintf nil "%s\\meta.txt" outDir))

    ; 1) ensure directories exist
    (obcMkdirWin outRoot)
    (obcMkdirWin outDir)

    ; 2) write meta first
    (obcWriteTextFile metaPath
      (list
        (sprintf nil "boardPath=%s" boardPath)
        (sprintf nil "outDir=%s" outDir)
        "tool=Allegro 17.40.035"
        "stage=init_ok"
      )
    )

    ; 3) generate minimal batch script
    (setq cmdLines
      (list
        (sprintf nil "set logfile \"%s\"" logPath)
        "set logfile_mode append"
        "echo === START ==="
        (sprintf nil "open \"%s\"" boardPath)
        "echo board_open_ok"
        "echo === END ==="
        "exit"
      )
    )
    (obcWriteTextFile cmdPath cmdLines)

    ; 4) run allegro batch (no redirect to avoid escaping issues)
    (axlShell(sprintf nil "allegro -batch -s \"%s\"" cmdPath))

    (printf "Done. Check folder: %s\n" outDir)
    t
  )
)
