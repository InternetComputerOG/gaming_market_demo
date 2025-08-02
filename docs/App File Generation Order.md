# App File Generation Order
1. Generate .env  
2. Generate .env_context.md  

3. Generate .env.example  
4. Generate .env.example_context.md  

5. Generate .gitignore  
6. Generate .gitignore_context.md  

7. Generate app/__init__.py  
8. Generate app__init__.py_context.md  

9. Generate app/services/__init__.py  
10. Generate app_services__init__.py_context.md  

11. Generate app/db/__init__.py  
12. Generate app_db__init__.py_context.md  

13. Generate app/engine/__init__.py  
14. Generate app_engine__init__.py_context.md  

15. Generate app/engine/tests/__init__.py  
16. Generate app_engine_tests__init__.py_context.md  

17. Generate app/runner/__init__.py  
18. Generate app_runner__init__.py_context.md  

19. Generate app/scripts/__init__.py  
20. Generate app_scripts__init__.py_context.md  

21. Generate app/config.py  
22. Generate config.py_context.md  

23. Generate app/utils.py  
24. Generate utils.py_context.md  

25. Generate app/db/schema.sql  
26. Generate schema.sql_context.md  

27. Generate app/db/queries.py  
28. Generate queries.py_context.md  

29. Generate app/db/migrations/001_initial.sql  
30. Generate 001_initial.sql_context.md  

31. Generate app/db/migrations/002_add_gas_metrics.sql  
32. Generate 002_add_gas_metrics.sql_context.md  

33. Generate app/engine/params.py  
34. Generate params.py_context.md  

35. Generate app/engine/state.py  
36. Generate state.py_context.md  

37. Generate app/engine/amm_math.py  
38. Generate amm_math.py_context.md  

39. Generate app/engine/impact_functions.py  
40. Generate impact_functions.py_context.md  

41. Generate app/engine/autofill.py  
42. Generate autofill.py_context.md  

43. Generate app/engine/lob_matching.py  
44. Generate lob_matching.py_context.md  

45. Generate app/engine/orders.py  
46. Generate engine_orders.py_context.md  

47. Generate app/engine/resolutions.py  
48. Generate engine_resolutions.py_context.md  

49. Generate app/services/realtime.py  
50. Generate realtime.py_context.md  

51. Generate app/services/orders.py  
52. Generate services_orders.py_context.md  

53. Generate app/services/positions.py  
54. Generate positions.py_context.md  

55. Generate app/services/resolutions.py  
56. Generate services_resolutions.py_context.md  

57. Generate app/services/ticks.py  (Note: Generate without runner/batch_runner.py_context.md initially, using the implementation plan for batch_runner integration details; refine if needed after generating runner.)  
58. Generate ticks.py_context.md  

59. Generate app/runner/batch_runner.py  
60. Generate batch_runner.py_context.md  

(go back to 57)

61. Generate app/runner/timer_service.py  
62. Generate timer_service.py_context.md  

63. Generate app/scripts/seed_config.py  
64. Generate seed_config.py_context.md  

65. Generate app/scripts/export_csv.py  
66. Generate export_csv.py_context.md  

67. Generate app/scripts/generate_graph.py  
68. Generate generate_graph.py_context.md  

69. Generate app/streamlit_app.py  
70. Generate streamlit_app.py_context.md  

71. Generate app/streamlit_admin.py  
72. Generate streamlit_admin.py_context.md  

73. Generate app/static/style.css  
74. Generate style.css_context.md  

75. Generate app/engine/tests/test_state.py  
76. Generate test_state.py_context.md  

77. Generate app/engine/tests/test_params.py  
78. Generate test_params.py_context.md  

79. Generate app/engine/tests/test_amm_math.py  
80. Generate test_amm_math.py_context.md  

81. Generate app/engine/tests/test_impact_functions.py  
82. Generate test_impact_functions.py_context.md  

83. Generate app/engine/tests/test_autofill.py  
84. Generate test_autofill.py_context.md  

85. Generate app/engine/tests/test_lob_matching.py  
86. Generate test_lob_matching.py_context.md  

87. Generate app/engine/tests/test_orders.py  
88. Generate test_orders.py_context.md  

89. Generate app/engine/tests/test_resolutions.py  
90. Generate test_resolutions.py_context.md  

91. Generate requirements.txt  
92. Generate requirements.txt_context.md  

93. Generate setup.py  
94. Generate setup.py_context.md  

95. Generate README.md 

(Note: app/static/logo.png is a binary image; do not generate it with the LLM—instead, source or create a placeholder manually and skip its context file.)

## Groupings of _context.md Files

### Group 1: 1_context.md
- .env_context.md
- .gitignore_context.md
- app__init__.py_context.md
- app_services__init__.py_context.md
- app_db__init__.py_context.md
- app_engine__init__.py_context.md
- app_engine_tests__init__.py_context.md
- app_runner__init__.py_context.md
- app_scripts__init__.py_context.md

### Group 2: 2_context.md
- config.py_context.md
- utils.py_context.md
- schema.sql_context.md
- queries.py_context.md
- 001_initial.sql_context.md
- 002_add_gas_metrics.sql_context.md

### Group 3: 3_context.md
- params.py_context.md
- state.py_context.md
- amm_math.py_context.md
- impact_functions.py_context.md
- autofill.py_context.md
- lob_matching.py_context.md
- engine_orders.py_context.md
- engine_resolutions.py_context.md

### Group 4: 4_context.md
- realtime.py_context.md
- services_orders.py_context.md
- positions.py_context.md
- services_resolutions.py_context.md
- ticks.py_context.md
- batch_runner.py_context.md
- timer_service.py_context.md

### Group 5: 5_context.md
- seed_config.py_context.md
- export_csv.py_context.md
- generate_graph.py_context.md
- style.css_context.md
- streamlit_app.py_context.md
- streamlit_admin.py_context.md

### Group 6: 6_context.md
- test_state.py_context.md
- test_params.py_context.md
- test_amm_math.py_context.md
- test_impact_functions.py_context.md
- test_autofill.py_context.md
- test_lob_matching.py_context.md
- test_orders.py_context.md
- test_resolutions.py_context.md
- requirements.txt_context.md
- setup.py_context.md