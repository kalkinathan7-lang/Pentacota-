import unittest
import pandas as pd
from pentacota.indicators import add_indicators
from pentacota.risk import position_size

class TestPentacota(unittest.TestCase):
    def test_indicators(self):
        n=250
        df=pd.DataFrame({"open":range(1,n+1),"high":range(2,n+2),"low":range(n),"close":range(1,n+1),"volume":[100]*n,"time":pd.date_range("2024-01-01",periods=n,freq="h",tz="UTC")})
        x=add_indicators(df)
        self.assertIn("ema200",x)
        self.assertTrue(x.ema200.notna().all())
    def test_position_size(self):
        self.assertAlmostEqual(position_size(10000,100,95,0.5),10)
        self.assertEqual(position_size(10000,100,100,0.5),0)

if __name__ == "__main__": unittest.main()
