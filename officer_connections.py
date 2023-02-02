## streamlit run "C:\Users\Jack\Documents\Python_projects\uk_companies_house_byAPI\officer_connections.py"

import numpy as np
import pandas as pd
from requests import get
import re
import requests
import streamlit as st
import streamlit.components.v1 as components

headers = {
    "api_key": st.secrets['api_key'],
    "content-type": "application/json"
}

### functions

def unpack_json_into_dataframe(v):
    
    df = pd.DataFrame()

    def unpack_json(v, prefix=''):

        if isinstance(v, dict):
            for k, v2 in v.items():
                p2 = "{}['{}']".format(prefix, k)
                px = re.findall("(\w+)",p2)
                px = ':'.join(px).strip()

                unpack_json(v2, px)

        elif isinstance(v, list):
            for i, v2 in enumerate(v):
                p2 = "{}[{}]".format(prefix, i)
                pn = re.findall("\[(.*)\]",p2)[0]
                px = re.sub("\[(.*)\]", f':{pn}', p2)

                unpack_json(v2, px)

        else:
        
            val = repr(v)[1:-1] if repr(v)[0] == "'" and repr(v)[-1] == "'" else repr(v)
            df.loc[0, prefix] = val
                    
    unpack_json(v)
    
    return df


############################
####### SUBFUNCTIONS #######
############################

#### Access the data from the UK Companies House REST API
def getJS(search_url, params):
    company_response = requests.get(search_url, auth=(api_key, ''), params=params)
    js = company_response.json() 
    return js

def miniUnpack(df, js, selected_columns):
            
    ### Unpack a few specific keys/values
    for key in [key for key in selected_columns if key in js.keys()]:
        if type(js[key]) == dict:
            for subkey in js[key].keys():
                df[f'{key.strip()}:{subkey.strip()}'] = js[key][subkey]
        else:
            df[key.strip()] = js[key]
                    
    return df
    
### For ease of analysis, assign all NaN birth values to 0, make all birth values integers
def updateBirthDateDetails(df):
    for column in [column for column in ['date_of_birth:year', 'date_of_birth:month'] if column in df.columns]:
        df[column] = df[column].fillna(0).astype(int)
    return df

## for sorting out active statuses
def getActiveStatus(df):
    for column in [column for column in ['appointed_on', 'resigned_on'] if column not in df.columns]:
        df[column] = None
    df['active'] = np.where(df['appointed_on'].isnull() & df['resigned_on'].isnull(), -1, np.where(df['appointed_on'].notnull() & df['resigned_on'].isnull(), 1, 0))       
    return df

## for neating dataframe at end
def orderColumns(df, first_columns, exclude_columns):        
    ordered_columns = [x for x in first_columns if x in df.columns] + [x for x in df.columns if x not in first_columns and x not in exclude_columns]
    return df[ordered_columns]



##################################
####### PRIMARY FUNCTIONS #######
##################################

def findPersonListings(search_term):
    
    df = pd.DataFrame()
    
    ### Get data from UKCH API
    js = getJS(f"https://api.company-information.service.gov.uk/search/officers", {'q':search_term, 'items_per_page': '100'})
    
    ### Unpack each line and concatenate it
    ### Uses the "unpack..." function, as each item has nested values
    for item in js['items']:        
        df = pd.concat([df,unpack_json_into_dataframe(item)]).reset_index(drop=True)
    
    ### Extract the Officer ID from the link column 
    df['officer_id'] = df['links:self'].apply(lambda x: re.findall('/officers/(.*)/appoint',x)[0]) #.group(1)
        
    df = updateBirthDateDetails(df)
        
    ### From the "address snippet", extract the address data up to the locality, which gets its own column.
    for column in ['address:locality']:
        df[column] = df[column].fillna('NONE')    
    df['address_short'] = df.apply(lambda x: x['address_snippet'].split(x['address:locality'])[0].strip(), axis=1)
    df['address_short'] = np.where(df['address_short'].str[-1] == ',', df['address_short'].str[:-1], df['address_short'])  ## get rid of trailing comma
    
    df['kind'] = np.where(df['kind'].str.contains('#'), df['kind'].apply(lambda x : re.findall('#(.*)', x)[0]), df['kind'])
    
    ### Neaten
    first_columns = ['title', 'address_short', 'address:locality', 'address:country', 'date_of_birth:year', 'date_of_birth:month', 'appointment_count', 'kind', 'officer_id',]
    exclude_columns = [x for x in df.columns if 'address' in x and x not in first_columns] + [x for x in df.columns if 'matches' in x] + [x for x in df.columns if 'description' in x]  + ['snippet']
    df = orderColumns(df, first_columns, exclude_columns)
    
    return df

#####

def getOfficerAppointments(officer_ids):
    
    df = pd.DataFrame()
    
    #### Access the data from the UK Companies House REST API
    for officer_id in officer_ids:
        js = getJS(f'https://api.company-information.service.gov.uk/officers/{officer_id}/appointments', {}) # params is empty
        for item in js['items']:   ### Unpack each line and concatenate it. Plus add officer id to each subdf before concatting it
            dfx = unpack_json_into_dataframe(item)
            dfx['officer_id'] = officer_id                  
            df = pd.concat([df,dfx])     
        df = df.reset_index(drop=True)
                        
        df = miniUnpack(df, js, ['date_of_birth', 'kind', 'is_corporate_officer', 'links'])    
          
    ### Final updates and tidy up
    df = updateBirthDateDetails(df)
    df = getActiveStatus(df)
    first_columns = ['name', 'appointed_to:company_name', 'nationality', 'date_of_birth:year', 'date_of_birth:month', 'address:locality', 'address:country', 'active', 'appointed_on', 'resigned_on', 'officer_role', 'occupation', 'officer_id', 'appointed_to:company_number'] + [x for x in df.columns if 'address' in x]
    df = orderColumns(df, first_columns, [])
            
    return df

####

def getCompanyPeople(company_numbers):
    
    first_columns = ['name', 'company_name', 'nationality', 'country_of_residence', 'active', 'appointed_on', 'resigned_on', 'person_type', 'officer_role', 'date_of_birth:year', 'date_of_birth:month', 'company_number', 'officer_id']
    df = pd.DataFrame(columns=first_columns)
    
    for company_number in company_numbers:
        
        dfC = pd.DataFrame()
        
        company_name = None
        company_name_url = f"https://api.companieshouse.gov.uk/company/{company_number}"
        company_name_response = requests.get(company_name_url, auth=(api_key, ''))
        company_name_js = company_name_response.json()  
        if 'company_name' in company_name_js.keys():
            company_name = company_name_js['company_name']
        
        ### Get Officers ###

        company_url = f"https://api.companieshouse.gov.uk/company/{company_number}/officers"
        company_response = requests.get(company_url, auth=(api_key, ''))        
        js = company_response.json()

        if 'items' in js.keys():
            for item in js['items']:
                dfx = unpack_json_into_dataframe(item)
                dfx['person_type'] = 'Officer'
                dfC = pd.concat([dfC, dfx])


        ### Get PSCS ###

        company_url = f"https://api.companieshouse.gov.uk/company/{company_number}/persons-with-significant-control"
        company_response = requests.get(company_url, auth=(api_key, ''))
        js = company_response.json()
        
        if 'items' in js.keys():
            for item in js['items']:
                dfx = unpack_json_into_dataframe(item)
                dfx['person_type'] = 'PSC'
                dfC = pd.concat([dfC, dfx])
                
        dfC['company_number'] = company_number
        dfC['company_name'] = company_name
        df = pd.concat([df, dfC])
    
    df['officer_id'] = np.where(df['links:officer:appointments'].isnull(), '/officers/*****/appointments', df['links:officer:appointments'])
    df['officer_id'] = np.where(df['officer_id'].str.contains('appointments'), df['officer_id'].apply(lambda x: re.findall('/officers/(.*)/appointments', str(x))[0]), None)
    df['officer_id'] = np.where(df['officer_id']=='*****', None, df['officer_id'])
                
    ### Final updates and tidy up
    df = updateBirthDateDetails(df)
    df = getActiveStatus(df)
    df = orderColumns(df, first_columns, [])   
    df = df.reset_index(drop=True)
    
    df.to_csv('test.csv', index=False)
    
    return df

##################################################


st.write('Constituent Investigative Analytics Studio')

st.write('# UK COMPANIES HOUSE OFFICER CONNECTIONS CHECKER #####')
st.write('Find which other people are a business director is connected to in the boardroom.')
st.write('This tool uses the UKCH API to find an individual, all the businesses they are an officer of and all other officers involved in those business.')

#api_key = st.text_input('Please enter API key')
api_key = headers["api_key"]

if len(api_key) > 10:

    search_term = st.text_input('Who would like to search for?', 'edward sheringham')  # 'josh landy' lydia alexandra gordon 'simon pearce'

    if len(search_term) > 0:

        dfSEARCH = findPersonListings(search_term)
        dfDISPLAY = dfSEARCH
                
        opening_display_year = dfDISPLAY.loc[0, 'date_of_birth:year']
        opening_display_month = dfDISPLAY.loc[0, 'date_of_birth:month']
        display_year_options = sorted(dfSEARCH['date_of_birth:year'].unique())
        birth_year = st.selectbox('Selected birth year:', display_year_options, display_year_options.index(opening_display_year))    
        
        display_month = sorted(dfSEARCH.loc[dfSEARCH['date_of_birth:year'] == birth_year, 'date_of_birth:month'].unique()).index(opening_display_month) if birth_year == opening_display_year else 0
        birth_month = st.selectbox('Selected birth month:', 
                                   sorted(dfSEARCH.loc[dfSEARCH['date_of_birth:year'] == birth_year, 'date_of_birth:month'].unique()), 
                                  display_month)
        
        dfDISPLAY = dfSEARCH.loc[(dfSEARCH['date_of_birth:year'].isin([birth_year])) & (dfSEARCH['date_of_birth:month'].isin([birth_month]))]
        st.dataframe(dfDISPLAY)
        
        filter_year_month_index = list(dfSEARCH.loc[(dfSEARCH['date_of_birth:year'] == birth_year) & (dfSEARCH['date_of_birth:month'] == birth_month)].index)
        
        selected_options = st.multiselect(
            'Individuals frequently have multiple officer identification numbers in the UK Companies House database. We aren\'t sure why either.\n\nIn any case, these are the rows from the spreadsheet above that we will look for, based on what you have enetered above.', 
            [x for x in range(0,dfSEARCH.shape[0])], 
            filter_year_month_index)
                
        proceed = st.radio('Ready to go?', ['no', 'yes'], horizontal=True)

        if proceed == 'yes':

            st.write('Getting data ...')

            officer_ids = dfSEARCH.loc[selected_options, 'officer_id'].to_list()

            st.write('Officer IDs: ', ', '.join(officer_ids))

            dfAPPOINTMENTS = getOfficerAppointments(officer_ids)
            
            company_numbers = dfAPPOINTMENTS['appointed_to:company_number'].unique()

            if len(company_numbers) > 0:

                st.write('Searching for who is involved with these companies:')
                
                #st.dataframe(dfAPPOINTMENTS)

                dfCOMPANYPEOPLE = getCompanyPeople(company_numbers)
                
                dfDISPLAY = dfCOMPANYPEOPLE
                st.write('---')

                all_individuals = list(dfCOMPANYPEOPLE['name'].unique())

                st.write('These are the people connected to the person(s) who searched for:')
                
                ######################
                
                import plotly.graph_objects as go
                from pyvis.network import Network
                import pyvis
                import math 
                
                def makePlotPYVIS(df, company_name_column):
                                        
                    dfPLOT = df.copy()
                    dfPLOT['name'] = np.where(dfPLOT['name'].str.contains(','), dfPLOT['name'], dfPLOT['name'] + ', ')
                    dfPLOT['name'] = dfPLOT['name'].apply(lambda x: x.split(',')[1] + ' ' + x.split(',')[0]).str.upper().str.strip()
                    
                    for index, row in dfPLOT.iterrows():
                        name = row['name']
                        if name.split(' ')[0] in ['MRS', 'MS', 'MISS', 'MR']:
                            dfPLOT.loc[index, 'name'] = ' '.join(name.split(' ')[1:])
                                                        
                    g = Network(height=1500, width=800, notebook=True, directed=False)
                    
                    ### Add person nodes
                    for index, row in dfPLOT.iterrows():
                                            
                        source, target = row['name'], row[company_name_column]
                    
                        ### Add person nodes
                        node_size = 10
                        node_shape = 'dot'
                        if row['officer_id'] in officer_ids:
                            node_size = 25
                            node_color = 'rgba(200, 200, 0, 0.8)'
                            node_shape = 'circularImage'
                            node_image = 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ0D8RJLIfGu9BfAEv3oMYyxiGfkGsGABeSsY6K2Ugy&s'
                        elif row['active'] == 1:
                            node_color = 'rgba(125, 125, 222, 0.6)'
                        elif row['active'] == -1:
                            node_color = 'rgba(125, 125, 222, 0.4)'
                        elif row['active'] == 0:
                            node_color = 'rgba(125, 125, 222, 0.2)'
                        else:
                            node_color = 'rgba(0, 0, 0, 1)' 
                         
                        g.add_node(source, color=node_color, size=node_size, shape = 'dot', title=source, font=(f'12 Manrope rgba(22,22,22,1)'))

                        ### company nodes
                        target_node_size = 10
                        target_node_color = 'rgba(0, 150, 100, 0.5)'
                        g.add_node(target, color=target_node_color, size=target_node_size, shape='dot', title=target, font=(f'12 Manrope rgba(22,22,22,1)'),)
                        
                        g.add_edge(source, target, weight=5, title='x', color='black')
                    
                    
                    ### display
                    path = '/tmp'
                    g.save_graph(f'temp.html')
                    HtmlFile = open(f'temp.html', 'r', encoding='utf-8')
                    components.html(HtmlFile.read(), height=550, width=700)
                    
                makePlotPYVIS(dfCOMPANYPEOPLE, 'company_name')
                
                
                
                
                
                ############### VISUALISE ############################
                
                import plotly.graph_objects as go
                import networkx as nx
                
                import pyvis
                             
                    
                def makePlot(dfPLOT, company_name_column):
                    
                    G = nx.Graph()
                    for index, row in dfPLOT.iterrows():

                        node_name, node_company = row['name'], row[company_name_column]

                        node_size = 10
                        if row['officer_id'] in officer_ids:
                            node_size = 25
                            name_node_color = 'rgba(200, 200, 0, 0.8)'
                        elif row['active'] == 1:
                            name_node_color = 'rgba(200, 200, 222, 0.8)'
                        elif row['active'] == 0:
                            name_node_color = 'rgba(200, 200, 222, 0.2)'
                        else:
                            name_node_color = 'rgba(22,22,22, 1s)'

                        G.add_node(node_name, color=name_node_color, size=node_size)
                        G.add_node(node_company, color='rgba(180,150,150,0.8)')
                        G.add_edge(node_name, node_company)
                        
                    fig = pyvis.network.Network(height= 700, width=700, directed=False)

                    fig.from_nx(G)

                    path = '/tmp'
                    fig.save_graph(f'temp.html')
                    HtmlFile = open(f'temp.html', 'r', encoding='utf-8')

                    components.html(HtmlFile.read(), height=700, width=700)
                    
                #makePlot(dfCOMPANYPEOPLE, 'company_name')
                    
                #################################
                
                st.write('More details:')
                st.dataframe(dfCOMPANYPEOPLE)
                
                #st.write('')
                #st.write('')
                #st.write('Looking for businesses of the associates:')
                
                #dfSECONDRINGBUSINESSES = getInnerCircle(dfCOMPANYPEOPLE)
                #st.dataframe(dfSECONDRINGBUSINESSES)
                
                #dfPLOT = pd.concat([dfCOMPANYPEOPLE, dfSECONDRINGBUSINESSES.rename(columns={'appointed_to:company_name':'company_name'})])
                #dfPLOT['name'] = np.where(dfPLOT['name'].str.contains(','), dfPLOT['name'], dfPLOT['name'] + ', ')
                #dfPLOT['name'] = dfPLOT['name'].apply(lambda x: x.split(',')[1] + ' ' + x.split(',')[0]).str.strip()
                #dfPLOT['name'] = np.where(dfPLOT['name'][0:2] == 'Mr', dfPLOT['name'][2:], dfPLOT['name'])
                #dfPLOT['name'] = dfPLOT['name'].str.upper()
                
                    
                #makePlot(dfPLOT, 'company_name')
                
                #st.dataframe(dfPLOT)
                
                st.write('')
                st.write('This is only the beginning of what we offer.')
                st.write('Want to see a more advanced option of the ([UKCH Network Mapper](https://constituent.au/data_visualisations/uk_companies_house_network_mapper_5309709_8081703_FC034703_04241161_05751462.html))?')
                st.write('Just email us the company IDs you are after and we will get back to you.')
                st.write('studio@constituent.au')
                
st.write('')
st.write('')
st.write('&#11041; More tools at www.constituent.au')