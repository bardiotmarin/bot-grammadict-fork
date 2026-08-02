import uiautomator2 as u2

def case_insensitive_re(str_match):
    """
    Exact implementation from GramAddict Utils
    """
    return f"(?i){str_match}"

d = u2.connect('127.0.0.1:21523')

# Try find
obj_re = d(resourceIdMatches=case_insensitive_re("com.instagram.android:id/action_bar_search_edit_text"))
obj_strict = d(resourceId="com.instagram.android:id/action_bar_search_edit_text")

print("Regex Matches exists:", obj_re.exists)
print("Strict Matches exists:", obj_strict.exists)

