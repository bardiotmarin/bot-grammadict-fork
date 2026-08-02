import GramAddict
import sys
try:
    from GramAddict.core import views
    print(f"DEBUG: GramAddict.core.views is loaded from: {views.__file__}")
except Exception as e:
    print(f"DEBUG: Could not import views: {e}")

GramAddict.run()
