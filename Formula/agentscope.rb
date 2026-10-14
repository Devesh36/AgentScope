class Agentscope < Formula
  desc "Local LLM monitoring, agent observability, and interactive investigation"
  homepage "https://github.com/Devesh36/AgentScope"
  url "https://github.com/Devesh36/AgentScope.git",
      using: :git,
      tag: "v0.4.2"
  version "0.4.2"

  depends_on "python@3.12"
  depends_on "node@24"
  depends_on "uv"

  def install
    # Service sources are prepared into a private runtime on the first watch.
    libexec.install "packages/cli/agentscope_cli"
    (libexec/"runtime/apps").mkpath
    (libexec/"runtime/apps").install "apps/api", "apps/web"
    (libexec/"runtime/packages").mkpath
    (libexec/"runtime/packages").install "packages/python-sdk"
    (bin/"agentscope").write <<~PYTHON
      #!#{Formula["python@3.12"].opt_bin}/python3.12
      import sys
      import os
      sys.dont_write_bytecode = True
      sys.path.insert(0, #{libexec.to_s.dump})
      os.environ["AGENTSCOPE_RUNTIME_SOURCE"] = #{(libexec/"runtime").to_s.dump}
      os.environ["PATH"] = #{(Formula["node@24"].opt_bin.to_s + ":").dump} + os.environ.get("PATH", "")
      from agentscope_cli.repl import main
      sys.exit(main())
    PYTHON
    (bin/"agentscope").chmod 0755
    bin.install_symlink bin/"agentscope" => "Agenscope"
  end

  test do
    assert_match "AgentScope 0.4.2", shell_output("#{bin}/agentscope --version")
    assert_match "watch", shell_output("#{bin}/agentscope --help")
    assert_path_exists libexec/"runtime/apps/api/app/main.py"
    assert_path_exists libexec/"runtime/apps/web/package-lock.json"
    assert_match "demo", pipe_output("#{bin}/Agenscope Repl", "help\nexit\n", 0)
  end
end
