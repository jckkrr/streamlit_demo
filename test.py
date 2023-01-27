## streamlit run "C:\Users\Jack\Documents\Python_projects\2023\streamlit\test.py"

import pandas as pd
import plotly.graph_objects as go
import networkx as nx
import streamlit as st
import streamlit.components.v1 as components
import pyvis

df = pd.DataFrame(columns=['source', 'target'])

df.loc[0] = 'Harry', 'Megan'
df.loc[1] = 'Harry', 'William'
df.loc[2] = 'William', 'Kate'

G = nx.from_pandas_edgelist(df, 'source', 'target', None)

fig = pyvis.network.Network(height=1000, width=1000, directed=False)

fig.from_nx(G)

#st.plotly_chart(fig, theme=None, use_container_width=True)

path = '/tmp'
fig.save_graph(f'temp.html')
HtmlFile = open(f'temp.html', 'r', encoding='utf-8')

components.html(HtmlFile.read(), height=435)
