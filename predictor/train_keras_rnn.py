from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, LSTM, Embedding, Dropout
from tensorflow.keras.optimizers import Adam
from tensorflow import config
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
import os
import sys
# from tokenization import return_tokens
# from julia import Main
# import h5py
# import hdf5plugin


print(config.list_physical_devices('GPU'))

# sudo cp /usr/lib/python3/dist-packages/tensorflow/libcudnn* /usr/lib/x86_64-linux-gnu/

''' give more stopping options '''

X = np.load(f'{os.getcwd()}//{sys.argv[1]}')
Y = np.load(f'{os.getcwd()}//{sys.argv[2]}')

# n = 60_000

# indicies = pd.DataFrame(range(len(X)), columns=['i'])
# indicies = indicies['i'].sample(n=n).to_numpy()

# sampled_X = np.zeros((n, X.shape[1], X.shape[2]))
# sampled_Y = np.zeros((n, Y.shape[1]))

# for n, i in enumerate(indicies):
#     sampled_X[n] = X[i]
#     sampled_Y[n] = Y[i]

trainX, testX, trainY, testY = train_test_split(X, Y, test_size=.1)
trainX.shape, testX.shape, trainY.shape, testY.shape

opt = Adam(.0001)
input_shape = trainX[0].shape

model = Sequential()
model.add(LSTM(514, input_shape=input_shape, activation="tanh", return_sequences=True, dropout=0.2)) 
model.add(LSTM(256, activation="tanh", return_sequences=True, dropout=0.2))
model.add(LSTM(128, activation="tanh", dropout=0.2))
model.add(Dense(64, activation="relu"))
model.add(Dropout(0.2))
model.add(Dense(32, activation="relu"))
model.add(Dropout(0.2))
model.add(Dense(16, activation="relu"))
model.add(Dropout(0.2))
model.add(Dense(2, activation="softmax"))

model.summary()

model.compile(loss='categorical_crossentropy', optimizer=opt, metrics=['accuracy'])

history = model.fit(trainX, trainY, batch_size=32, epochs=int(sys.argv[3]), validation_data=(testX, testY), verbose=1)

train_preds = model.predict(trainX)
test_preds = model.predict(testX)

hist_df = pd.DataFrame(history.history)

hist_df.to_csv(f'{os.getcwd()}//model_history.csv', index=False)
model.save(f'{os.getcwd()}//rnn_model.h5')

pd.DataFrame(train_preds).to_csv(f'{os.getcwd()}//train_preds.csv', index=False)
pd.DataFrame(test_preds).to_csv(f'{os.getcwd()}//test_preds.csv', index=False)
