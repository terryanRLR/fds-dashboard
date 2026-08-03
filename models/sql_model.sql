
SELECT
  CASE WHEN Customer_VPN_Indicator=1 AND Unused_terminal_status=1 THEN 0.6 ELSE 0.02 END AS proba_a,
  CASE WHEN Another_Person_Account=1 THEN 0.5 ELSE 0.03 END AS proba_c,
  CASE WHEN Customer_VPN_Indicator=0 AND Another_Person_Account=0 THEN 0.9 ELSE 0.2 END AS proba_m
FROM data
