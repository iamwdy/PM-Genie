
{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.python311Packages.setuptools
    pkgs.python311Packages.wheel
  ];
  
  env = {
    PYTHON_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
      pkgs.glib
      pkgs.xorg.libX11
      pkgs.glibc
    ];
    PYTHONHOME = "${pkgs.python311}";
    PYTHONPATH = "${pkgs.python311}/${pkgs.python311.sitePackages}";
  };
}
