import pandas as pd
import streamlit as st

import os

import random
    
df = pd.DataFrame(columns=['x','y'])
x = [x for x in range(1,11)]
power_n = st.slider('Power N', 0, 10, 1)

df['x'] = x
df['y'] = [x ** power_n for x in x]

st.line_chart(df, x='x', y='y')
