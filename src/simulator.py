'''
ver 0.1, namera@ , initial-release, Oct26'17
ver 0.2, namera@ , included execution id for traceability, Nov3'17
ver 0.3, shawo@  , Corrected typos in variable names, Apr23'18
ver 0.4, angelaw@  , Added S3 upload flag, removed risk calculations, Oct17'18


Hedge Your Own Funds: Running Monte Carlo Simulations on AWS Batch
=================================================================

This worker script launches the Monte-Carlo simulations.
All input parameters have defaults, please see 'parser.add_argument' for details or simply append -h at the end of the execution line to
see input parameter details.

e.g. python simulator.py -h

Output:
-------
This script writes simualted results into CSV files, the files are:
<exec_id>_<Stock_Name>_MonteCarloSimResult.csv - for example, AMZN_MonteCarloSimResult.csv , this file holds the last Monte-Carlo simulated value
 for each iteration and the expected cache value given the trading strategy specified in the notebook. Initial investment is $100,000
portfolioRiskAssessment.csv - returns the risk value of multiple-socks portfolio. see --portfolio_stocks_list input paramter for more detai$


Sample executions:
------------------
Run simulation with default parameters:
python simulator.py

Specify 1,000,000 simulations to execute:
python simulator.py --iterations 1000000
'''

import pandas as pd
from pandas_datareader import data as pdr
import numpy as np
import datetime, time
from math import sqrt
# from scipy.stats import norm
import yfinance as yf
import boto3
import uuid
import subprocess

import argparse

s3 = boto3.client('s3')


# Save the simulation results to an S3 bucket
def saveToS3(bucket_name, filename, STOCK):
    if bucket_name is not None:
        s3.upload_file(filename, bucket_name, "simulation-results/stock=" + STOCK + "/" + filename)
        print("Finished uploading " + filename + "to s3.")
        subprocess.check_output(['rm', filename])
    else:
        print("skipping s3 upload as no bucket is specified")


def setup_cmd_parser():
    parser = argparse.ArgumentParser(description='Running Monte Carlo Simulations for stock purchases.')
    parser.add_argument('--iterations', dest='iterations', default=100, type=int,
                        help='Number of simulated iterations default=100')
    parser.add_argument('--stock', dest='stock', default="AMZN",
                        help='Stock Name')
    parser.add_argument('--short_window_days', dest='short_window_days', default=10, type=int,
                        help='Short moving avearge in days default=10')
    parser.add_argument('--long_window_days', dest='long_window_days', default=40, type=int,
                        help='Long moving avearge in days (default=40)')
    parser.add_argument('--trading_days', dest='trading_days', default=252, type=int,
                        help='Number of trading days (default=252)')
    parser.add_argument('--s3_bucket', dest='s3_bucket', default=None,
                        help='S3 bucket to upload results to. If not provided, the results will not be uploaded to S3.')
    return parser


def run_simulations(parser):
    args = parser.parse_args()

    STOCK = args.stock
    short_window = args.short_window_days
    long_window = args.long_window_days
    trading_days = args.trading_days
    sim_num = args.iterations
    print("running " + str(sim_num) + " iterations")
    # portfolio_stocks_list = args.stocks_list
    s3_bucket = args.s3_bucket

    # create output files (CSV) unique string to preapend
    # if (file_prepend_str == 'None'):
    #     t = time.localtime()
    #     file_prepend_str = time.strftime('%b-%d-%Y_%H%M', t)
    t = time.localtime()
    file_prepend_str = time.strftime('%b-%d-%Y_%H%M%S', t)

    # Import stock information to dataframe. ADDED 04/2018 - Fix for yahoo finance
    yf.pdr_override()
    stock_df = pdr.get_data_yahoo(STOCK, start=datetime.datetime(2006, 10, 1), end=datetime.datetime(2017, 10, 1))

    # Calculate the compound annual growth rate (CAGR) which
    # will give us our mean return input (mu)
    days = (stock_df.index[-1] - stock_df.index[0]).days
    cagr = ((((stock_df['Adj Close'][-1]) / stock_df['Adj Close'][1])) ** (365.0 / days)) - 1
    mu = cagr

    # create a series of percentage returns and calculate
    # the annual volatility of returns. Generally, the higher the volatility,
    # the riskier the investment in that stock, which results in investing in one over another.
    stock_df['Returns'] = stock_df['Adj Close'].pct_change()
    vol = stock_df['Returns'].std() * sqrt(252)

    # Set the initial capital
    initial_capital = float(100000.0)

    # Set up empty list to hold our ending values for each simulated price series
    sim_result = []

    # Set up empty list to hold portfolio value for each simulated price serries, this is the value of position['total']
    portfolio_total = []

    # Define Variables
    start_price = stock_df['Adj Close'][-1]  # starting stock price (i.e. last available real stock price)

    # Initialize the `signals` DataFrame
    signals = pd.DataFrame()

    # Initialize by setting the value for all rows in this column to 0.0.
    signals['signal'] = 0.0
    signals['short_mavg'] = 0.0

    # Create a DataFrame `positions`
    positions = pd.DataFrame(index=signals.index).fillna(0.0)

    # Choose number of runs to simulate - I have chosen 1,000
    for i in range(sim_num):
        # create list of daily returns using random normal distribution
        daily_returns = np.random.normal(mu / trading_days, vol / sqrt(trading_days), trading_days) + 1

        # Set starting price and create price series generated by above random daily returns
        price_list = [start_price]

        for x in daily_returns:
            price_list.append(price_list[-1] * x)

        # Convert list to Pandas DataFrame
        price_list_df = pd.DataFrame(price_list)

        # Append the ending value of each simulated run to the empty list we created at the beginning
        sim_result.append(price_list[-1])

        # Create short simple moving average over the short & long window
        signals['short_mavg'] = price_list_df[0].rolling(short_window).mean()
        signals['long_mavg'] = price_list_df[0].rolling(long_window).mean()

        # Create a signal when the short moving average crosses the long moving average,
        # but only for the period greater than the shortest moving average window.
        signals['signal'][short_window:] = np.where(signals['short_mavg'][short_window:]
                                                    > signals['long_mavg'][short_window:], 1.0, 0.0)

        # Generate trading orders
        signals['positions'] = signals['signal'].diff()

        # Buy 100 shares
        positions[STOCK] = 100 * signals['signal']

        # Initialize the portfolio with value owned
        portfolio = positions.multiply(price_list_df[0], axis=0)

        # Store the difference in shares owned
        pos_diff = positions.diff()

        # Add `holdings` to portfolio
        portfolio['holdings'] = (positions.multiply(price_list_df[0], axis=0)).sum(axis=1)

        # Add `cash` to portfolio
        portfolio['cash'] = initial_capital - (pos_diff.multiply(price_list_df[0], axis=0)).sum(axis=1).cumsum()

        # Add `total` to portfolio
        portfolio['total'] = portfolio['cash'] + portfolio['holdings']

        # Append the ending value of each simulated run to the empty list we created at the beginning
        portfolio_total.append(portfolio['total'].iloc[-1])

    # Simulation Results
    # print sim_result
    df1 = pd.DataFrame(sim_result, columns=["MonteCarloResults"])

    # Portfolio Total
    # Print portfolio_total
    df2 = pd.DataFrame(portfolio_total, columns=["portfolioTotal"])

    # Create one data frame and write to file.
    df3 = pd.concat([df1, df2], axis=1)
    df3 = df3.reindex(df1.index)
    joined_result_file = file_prepend_str + "_" + STOCK + "_" + (str(uuid.uuid4()))[:6] + "_MonteCarloSimResult.csv"
    df3.to_csv(joined_result_file)
    saveToS3(s3_bucket, joined_result_file, STOCK)


if __name__ == "__main__":
    parser = setup_cmd_parser()
    run_simulations(parser)
