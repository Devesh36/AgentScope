class Agentscope < Formula
  desc "Interactive agent observability and synthetic incident demo client"
  homepage "https://github.com/Devesh36/AgentScope"
  url "https://github.com/Devesh36/AgentScope.git",
      using: :git,
      revision: "ed613783861967ca3b5003d170cf0bb3172acf8a"
  version "0.2.0"

  depends_on "python@3.12"

  def install
    # The client has no runtime dependencies. Install its source directly rather
    # than downloading build tools or running pip during Homebrew installation.
    libexec.install "packages/cli/agentscope_cli"
    (bin/"agentscope").write <<~PYTHON
      #!#{Formula["python@3.12"].opt_bin}/python3.12
      import sys
      sys.dont_write_bytecode = True
      sys.path.insert(0, #{libexec.to_s.dump})
      from agentscope_cli.repl import main
      sys.exit(main())
    PYTHON
    (bin/"agentscope").chmod 0755
    bin.install_symlink bin/"agentscope" => "agenscope"
    bin.install_symlink bin/"agentscope" => "Agenscope"
  end

  test do
    assert_match "AgentScope 0.2.0", shell_output("#{bin}/agentscope --version")
    assert_match "demo", pipe_output("#{bin}/Agenscope Repl", "help\nexit\n", 0)
  end
end
