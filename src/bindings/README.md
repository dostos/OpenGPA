# Python Bindings

pybind11 bindings for OpenGPA's C++ core engine. Exposes `Engine`, `QueryEngine`, and associated data types so the Python layer can start/stop capture sessions and issue frame queries without subprocess overhead.

## Key Files
- `py_gpa.cpp` — single-file binding; defines the `_gpa_native` extension module

## See Also
- `src/core/README.md` — C++ engine being wrapped
- `src/python/gpa/backends/README.md` — Python backend that imports this module
