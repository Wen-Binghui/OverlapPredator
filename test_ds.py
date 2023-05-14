import numpy as np

score = np.random.rand(4,4)
print(score)

row = np.argmax(score, axis=0)
print(row)
# ds = np.load('data/3dlo-preprocess-nomutual/fcgf/7-scenes-redkitchen/6_3_feature_src.npy')
# print(ds.shape)