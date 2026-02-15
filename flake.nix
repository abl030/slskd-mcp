{
  description = "AI-generated MCP server for the slskd API v0";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = {
    self,
    nixpkgs,
  }: let
    forAllSystems = nixpkgs.lib.genAttrs [
      "x86_64-linux"
      "aarch64-linux"
    ];
  in {
    packages = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      pythonEnv = pkgs.python3.withPackages (ps: [
        ps.fastmcp
        ps.httpx
      ]);
    in {
      default = pkgs.writeShellApplication {
        name = "slskd-mcp";
        runtimeInputs = [pythonEnv];
        text = ''
          exec fastmcp run ${./generated/server.py}
        '';
      };
    });

    checks = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      pythonEnv = pkgs.python3.withPackages (ps: [
        ps.fastmcp
        ps.httpx
        ps.jinja2
        ps.pytest
        ps.pytest-asyncio
        ps.pytest-timeout
      ]);
    in {
      unit-tests = pkgs.runCommand "slskd-mcp-unit-tests" {
        nativeBuildInputs = [pythonEnv];
      } ''
        cp -r ${./.} src
        cd src
        python -m pytest tests/ -m "not integration" -q
        touch $out
      '';
    });

    devShells = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      pythonEnv = pkgs.python3.withPackages (ps: [
        ps.fastmcp
        ps.httpx
        ps.jinja2
        ps.pytest
        ps.pytest-asyncio
        ps.pytest-timeout
      ]);
    in {
      default = pkgs.mkShell {
        packages = [pythonEnv pkgs.gnumake];
      };
    });
  };
}
