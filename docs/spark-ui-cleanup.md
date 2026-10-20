# Spark UI and naming cleanup

The command center owns workspace navigation. Embedded WorkspacePanel and IntelligenceConsole render their selected content without competing tab bars, home headers, or sidebars. Missions and Memory open their intelligence controls directly. All intelligence tools remain reachable through grouped command-center destinations. Document publishing controls appear only with document knowledge. Standalone panels retain their navigation.

The Python engine is backend/spark.py. Server imports, self-healing module selection, voice file references, tests, CI, setup instructions, and runtime log/speaker labels use Spark. The historical speaker alias in ChatModule remains supported for saved conversations. Third-party notices and historical audit records retain upstream identity and URLs; trace.txt is historical evidence.

The active checkout and Git remote were already named spark. The desktop batch launcher and SPARK shortcut now target C:/Users/ASUS/spark. The separate, modified older checkout was preserved as C:/Users/ASUS/spark-legacy. Its historical sources and data remain unchanged; its old virtual environment may contain absolute paths and should be recreated before running that legacy checkout.

Validation: production Vite build; 103 existing JavaScript tests passed, one skipped; two navigation rendering tests passed; ten live-configuration tests and six persistent-conversation tests passed; Python compilation passed. No live microphone/hardware session or visual browser review was performed in this cleanup.
