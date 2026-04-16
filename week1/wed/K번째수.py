def solution(array, commands):
    answer = []
    for c in commands: # commands 리스트에 있는 요소 하나하나를 c에 넣어서 반복문
        newArr = array[c[0]-1:c[1]] # c[0]번째 수부터 c[1]번째 수까지의 새 리스트를 만듦
        newArr.sort() # 리스트를 정렬
        answer.append(newArr[c[2]-1]) #정렬한 리스트의 c[2]번째 수를 answer 리스트에 push함
    return answer