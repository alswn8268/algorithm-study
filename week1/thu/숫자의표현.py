def solution(n):
    answer = 1
    # 왼쪽 포인터: left / 오른쪽 포인터: right 
    for left in range(1, (n+1)//2):
        right, sum = left, left # 연속합의 처음값과 오른쪽 포인터도 left와 같은 값에서부터 시작함
        while (left <= right):
            if (sum == n):
                answer += 1
                break
            elif (sum < n):
                right += 1
                sum += right
            else:
                break
    return answer